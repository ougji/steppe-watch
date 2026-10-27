"""Bounded Sentinel-2 acquisition with quality checks on the requested region.

Earth Search Collection 1 supplies public COGs and reliable reflectance offsets.
Scene-wide cloud metadata is only a prefilter. SCL, coverage and RGB nodata are
checked locally before a pair can enter the existing RGB comparison pipeline.
"""

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from scipy.ndimage import maximum_filter
from shapely.geometry import mapping, shape
from shapely.validation import explain_validity

API_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
EARLIEST_DATE = date(2017, 1, 1)
MAX_PIXELS = 4_000_000
MAX_AREA_KM2 = 400
CLEAR_CLASSES = (4, 5, 6)
CLOUD_CLASSES = (3, 8, 9, 10)  # shadow, medium/high cloud, cirrus
DISPLAY_MAX_REFLECTANCE = 0.3


class SatelliteError(ValueError):
    """A recoverable input, catalogue or acquisition error."""


class NoClearPair(SatelliteError):
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def normalize_aoi(geojson):
    """Accept one valid WGS84 Polygon, including a Leaflet rectangle."""
    if not isinstance(geojson, dict):
        raise SatelliteError("Draw a rectangle or polygon on the map first.")
    if geojson.get("type") == "Feature":
        geojson = geojson.get("geometry", {})
    try:
        polygon = shape(geojson)
    except (TypeError, ValueError, KeyError) as error:
        raise SatelliteError("The selected region is not a valid GeoJSON polygon.") from error
    if polygon.geom_type != "Polygon" or polygon.is_empty or polygon.has_z:
        raise SatelliteError("Select one nonempty, two-dimensional polygon.")
    if not polygon.is_valid:
        raise SatelliteError(f"Redraw the region: {explain_validity(polygon)}.")
    coordinates = np.asarray(
        [p for ring in (polygon.exterior, *polygon.interiors) for p in ring.coords]
    )
    if len(coordinates) > 2000 or not np.isfinite(coordinates).all():
        raise SatelliteError("Use a finite polygon with at most 2,000 vertices.")
    west, south, east, north = polygon.bounds
    if not (-180 <= west < east <= 180 and -80 <= south < north <= 84):
        raise SatelliteError(
            "Choose a region between 80°S and 84°N, without crossing the date line."
        )
    if east - west > 2 or north - south > 2:
        raise SatelliteError("Select a smaller region (at most 400 km²).")
    return json.loads(json.dumps(mapping(polygon)))


@dataclass(frozen=True)
class QualityPolicy:
    max_scene_cloud_percent: float = 20.0
    max_aoi_cloud_percent: float = 0.0
    min_usable_percent: float = 100.0
    cloud_buffer_m: int = 60

    def __post_init__(self):
        for name in ("max_scene_cloud_percent", "max_aoi_cloud_percent", "min_usable_percent"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 <= value <= 100
            ):
                raise SatelliteError("Cloud and usable-coverage limits must be between 0 and 100%.")
        if self.min_usable_percent <= 0:
            raise SatelliteError("Minimum usable coverage must be greater than zero.")
        if (
            isinstance(self.cloud_buffer_m, bool)
            or not isinstance(self.cloud_buffer_m, int)
            or not 0 <= self.cloud_buffer_m <= 200
        ):
            raise SatelliteError("The cloud buffer must be an integer between 0 and 200 metres.")


@dataclass(frozen=True)
class SatelliteRequest:
    aoi: dict
    start: date
    end: date
    window_days: int = 14
    resolution_m: int = 10
    policy: QualityPolicy = QualityPolicy()

    def __post_init__(self):
        object.__setattr__(self, "aoi", normalize_aoi(self.aoi))
        if type(self.start) is not date or type(self.end) is not date:
            raise SatelliteError("Choose a start and end date using the calendars.")
        if not EARLIEST_DATE <= self.start < self.end <= datetime.now(timezone.utc).date():
            raise SatelliteError("Start must precede end; use dates from 2017 through today.")
        if (
            isinstance(self.window_days, bool)
            or not isinstance(self.window_days, int)
            or not 0 <= self.window_days <= 30
        ):
            raise SatelliteError("The search window must be between 0 and 30 days.")
        if isinstance(self.resolution_m, bool) or self.resolution_m not in (10, 20):
            raise SatelliteError("Choose a 10 m or 20 m comparison grid.")
        if not isinstance(self.policy, QualityPolicy):
            raise SatelliteError("Provide a valid imagery quality policy.")

    @property
    def windows(self):
        delta = timedelta(days=self.window_days)
        return (
            (self.start, min(self.start + delta, self.end)),
            (max(self.end - delta, self.start), self.end),
        )

    @property
    def key(self):
        value = {**asdict(self), "start": self.start.isoformat(), "end": self.end.isoformat()}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass
class CropGrid:
    crs: str
    transform: Affine
    width: int
    height: int
    aoi_mask: np.ndarray
    resolution_m: int
    area_km2: float

    def metadata(self):
        return {
            "crs": self.crs,
            "transform": list(self.transform)[:6],
            "width": self.width,
            "height": self.height,
            "resolution_m": self.resolution_m,
            "aoi_area_km2": self.area_km2,
        }


def make_grid(aoi, resolution_m=10):
    aoi = normalize_aoi(aoi)
    if isinstance(resolution_m, bool) or resolution_m not in (10, 20):
        raise SatelliteError("Choose a 10 m or 20 m comparison grid.")
    centroid = shape(aoi).centroid
    zone = min(60, max(1, int((centroid.x + 180) // 6) + 1))
    crs = f"EPSG:{(32600 if centroid.y >= 0 else 32700) + zone}"
    projected = transform_geom("EPSG:4326", crs, aoi)
    polygon = shape(projected)
    area_km2 = polygon.area / 1_000_000
    if not 0.01 <= area_km2 <= MAX_AREA_KM2:
        raise SatelliteError("Choose a region between 0.01 and 400 km².")
    west, south, east, north = polygon.bounds
    left = math.floor(west / resolution_m) * resolution_m
    top = math.ceil(north / resolution_m) * resolution_m
    width = math.ceil((east - left) / resolution_m)
    height = math.ceil((top - south) / resolution_m)
    if width * height > MAX_PIXELS:
        raise SatelliteError(
            "The crop exceeds 4 million pixels. Draw a smaller region or choose 20 m."
        )
    transform = from_origin(left, top, resolution_m, resolution_m)
    mask = geometry_mask([projected], (height, width), transform, invert=True)
    if not mask.any():
        raise SatelliteError("The selected polygon contains no pixel centres. Draw a wider region.")
    return CropGrid(crs, transform, width, height, mask, resolution_m, area_km2)


class EarthSearch:
    """Read-only STAC client with bounded, explicit pagination and timeouts."""

    def __init__(self, session=None, max_items=200):
        self.session = session or requests.Session()
        self.max_items = max_items

    def search(self, aoi, start, end):
        params = {
            "collections": COLLECTION,
            "bbox": ",".join(map(str, shape(aoi).bounds)),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59.999999Z",
            "limit": 100,
        }
        url, visited, items = f"{API_URL}/search", set(), {}
        while url:
            if url in visited or urlparse(url).netloc != urlparse(API_URL).netloc:
                raise SatelliteError("The imagery catalogue returned an invalid pagination link.")
            visited.add(url)
            try:
                response = self.session.get(url, params=params, timeout=(10, 45))
                response.raise_for_status()
                data = response.json()
                features = data["features"]
                if not isinstance(features, list):
                    raise ValueError("Invalid features")
                for item in features:
                    items[item["id"]] = item
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                raise SatelliteError(
                    "Cannot reach the satellite catalogue. Check the connection and try again."
                ) from error
            next_link = next(
                (link for link in data.get("links", []) if link.get("rel") == "next"), None
            )
            if len(items) > self.max_items or (len(items) >= self.max_items and next_link):
                raise SatelliteError(
                    "Too many scenes for a complete search. Use a smaller region or shorter window."
                )
            if next_link and next_link.get("method", "GET").upper() != "GET":
                raise SatelliteError(
                    "Unsupported catalogue pagination; retry with a shorter date window."
                )
            url = next_link.get("href") if next_link else None
            params = None
        return list(items.values())


def asset_href(scene, name):
    asset = scene.get("assets", {}).get(name, {})
    url = asset.get("href", "")
    parsed = urlparse(url)
    # The provider uses public HTTPS COGs; never accept local paths or requester-pays assets.
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".amazonaws.com")
        or parsed.username
        or parsed.password
    ):
        raise SatelliteError(f"The scene has no supported public {name} asset.")
    if scene.get("properties", {}).get("storage:requester_pays"):
        raise SatelliteError("This scene requires a paid storage account.")
    return url


def read_band(scene, name, grid, *, padding=0):
    """Read just this crop from a remote COG, warped onto one shared UTM grid."""
    transform = grid.transform * Affine.translation(-padding, -padding)
    # GDAL's bundled libcurl may not discover the same trust store as requests.
    # Honour explicitly configured bundles and keep TLS verification enabled.
    ca_bundle = (
        os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("CURL_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("GDAL_CURL_CA_BUNDLE")
        or requests.certs.where()
    )
    try:
        with rasterio.Env(
            GDAL_CURL_CA_BUNDLE=ca_bundle,
            CURL_CA_BUNDLE=ca_bundle,
            SSL_CERT_FILE=ca_bundle,
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            GDAL_HTTP_CONNECTTIMEOUT="10",
            GDAL_HTTP_TIMEOUT="45",
            GDAL_HTTP_MAX_RETRY="2",
            GDAL_HTTP_RETRY_DELAY="1",
            VSI_CACHE=True,
            VSI_CACHE_SIZE=5_000_000,
        ):
            with rasterio.open(asset_href(scene, name)) as source:
                with WarpedVRT(
                    source,
                    crs=grid.crs,
                    transform=transform,
                    width=grid.width + 2 * padding,
                    height=grid.height + 2 * padding,
                    resampling=Resampling.nearest,
                    nodata=0,
                ) as warped:
                    return warped.read(1, masked=True).filled(0)
    except (rasterio.errors.RasterioError, OSError) as error:
        raise SatelliteError(f"Could not read the {name} crop for this scene.") from error


def assess_scl(scl, aoi_mask, policy, resolution_m):
    """Keep only vegetation, bare land and water; measure inside the polygon."""
    if scl.shape != aoi_mask.shape or aoi_mask.dtype != np.bool_ or not aoi_mask.any():
        raise SatelliteError("Quality data must cover the crop and contain selected pixels.")
    cloud = np.isin(scl, CLOUD_CLASSES)
    radius = math.ceil(policy.cloud_buffer_m / resolution_m)
    if radius:
        cloud = maximum_filter(cloud, size=2 * radius + 1, mode="constant", cval=0)
    usable = np.isin(scl, CLEAR_CLASSES) & ~cloud & aoi_mask
    count = int(aoi_mask.sum())
    stats = {
        "aoi_pixels": count,
        "cloud_shadow_percent": float(100 * np.count_nonzero(cloud & aoi_mask) / count),
        "usable_percent": float(100 * usable.sum() / count),
        "data_coverage_percent": float(
            100 * np.count_nonzero((scl > 0) & (scl <= 11) & aoi_mask) / count
        ),
        "scl_class_counts": {
            str(value): int(np.count_nonzero((scl == value) & aoi_mask)) for value in range(12)
        },
    }
    return usable, stats


def quality_passes(stats, policy):
    return (
        stats["cloud_shadow_percent"] <= policy.max_aoi_cloud_percent + 1e-9
        and stats["usable_percent"] + 1e-9 >= policy.min_usable_percent
    )


def reflectance_rgb(scene, grid, reader=read_band):
    channels, nodata, scaling = [], np.zeros(grid.aoi_mask.shape, dtype=bool), {}
    for name in ("red", "green", "blue"):
        raw = reader(scene, name, grid)
        if raw.shape != grid.aoi_mask.shape:
            raise SatelliteError("The RGB asset did not cover the requested grid.")
        bands = scene["assets"][name].get("raster:bands", [])
        if not bands or "scale" not in bands[0] or "offset" not in bands[0]:
            raise SatelliteError(
                "Reflectance scale/offset metadata is missing; this scene cannot be compared safely."
            )
        scale, offset = float(bands[0]["scale"]), float(bands[0]["offset"])
        if not math.isfinite(scale) or scale <= 0 or not math.isfinite(offset):
            raise SatelliteError("Invalid reflectance scale/offset metadata.")
        nodata |= (raw == bands[0].get("nodata", 0)) | ~np.isfinite(raw)
        reflected = raw.astype(np.float32) * scale + offset
        channels.append(
            np.rint(np.clip(reflected / DISPLAY_MAX_REFLECTANCE, 0, 1) * 255).astype(np.uint8)
        )
        scaling[name] = {"scale": scale, "offset": offset}
    rgb = np.stack(channels, axis=-1)
    rgb[~grid.aoi_mask | nodata] = 0
    return rgb, ~nodata & grid.aoi_mask, scaling


@dataclass
class SceneCrop:
    scene: dict
    rgb: np.ndarray
    valid: np.ndarray
    scl: np.ndarray
    quality: dict
    scaling: dict


@dataclass
class SatellitePair:
    before: SceneCrop
    after: SceneCrop
    valid: np.ndarray
    grid: CropGrid
    provenance: dict
    diagnostics: list

    @property
    def metadata(self):
        return {
            "site": "Map-selected region",
            "source": f"{API_URL}/collections/{COLLECTION}",
            "before_date": self.before.scene["properties"]["datetime"][:10],
            "after_date": self.after.scene["properties"]["datetime"][:10],
            "notes": "Sentinel-2 Collection 1 L2A; shared UTM grid; fixed 0–0.3 reflectance RGB mapping. See satellite_provenance.json for region, scene IDs and quality checks.",
        }

    def artifacts(self):
        artifacts = {
            "aoi.geojson": (
                json.dumps(
                    {"type": "Feature", "properties": {}, "geometry": self.provenance["aoi"]},
                    indent=2,
                )
                + "\n"
            ).encode(),
            "satellite_provenance.json": (
                json.dumps(self.provenance, indent=2, allow_nan=False) + "\n"
            ).encode(),
        }
        for name, crop in (("before", self.before), ("after", self.after)):
            artifacts[f"{name}_scene.json"] = (json.dumps(crop.scene, indent=2) + "\n").encode()
            artifacts[f"{name}_scl.tif"] = geotiff_bytes(crop.scl, self.grid)
            artifacts[f"{name}_georeferenced.tif"] = geotiff_bytes(crop.rgb, self.grid)
        return artifacts


def geotiff_bytes(array, grid):
    pixels = array[np.newaxis, ...] if array.ndim == 2 else np.moveaxis(array, -1, 0)
    with rasterio.io.MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=grid.height,
            width=grid.width,
            count=pixels.shape[0],
            dtype=pixels.dtype,
            crs=grid.crs,
            transform=grid.transform,
            compress="deflate",
        ) as target:
            target.write(pixels)
        return memory.read()


def acquisition_time(scene):
    value = datetime.fromisoformat(scene["properties"]["datetime"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Missing timezone")
    return value.astimezone(timezone.utc)


def find_pair(request, *, client=None, reader=read_band, progress=None):
    """Find the nearest qualifying endpoint pair without relaxing any limits."""
    grid = make_grid(request.aoi, request.resolution_m)
    client = client or EarthSearch()
    diagnostics, cache, candidates = [], {}, []
    polygon = shape(request.aoi)
    for role, (start, end) in zip(("before", "after"), request.windows):
        if progress:
            progress(f"Searching {role} scenes: {start} to {end}…")
        rows = []
        for scene in client.search(request.aoi, start, end):
            try:
                instant = acquisition_time(scene)
                cloud = float(scene["properties"]["eo:cloud_cover"])
                if not start <= instant.date() <= end:
                    continue
                if (
                    scene.get("collection") != COLLECTION
                    or not math.isfinite(cloud)
                    or not 0 <= cloud <= 100
                ):
                    raise ValueError("Missing quality metadata")
                reason = None
                if not shape(scene["geometry"]).covers(polygon):
                    reason = "Scene does not cover the whole region"
                elif cloud > request.policy.max_scene_cloud_percent:
                    reason = "Scene-wide cloud limit exceeded"
                row = {
                    "role": role,
                    "scene_id": scene["id"],
                    "captured_utc": instant.isoformat(),
                    "scene_cloud_percent": cloud,
                    "status": reason or "Awaiting region check",
                }
                diagnostics.append(row)
                if reason is None:
                    rows.append((scene, row, instant))
            except (KeyError, ValueError, TypeError):
                diagnostics.append(
                    {
                        "role": role,
                        "scene_id": scene.get("id", "unknown"),
                        "status": "Invalid scene metadata",
                    }
                )
        rows.sort(
            key=lambda item: (
                item[2].date().toordinal() * (1 if role == "before" else -1),
                item[1]["scene_cloud_percent"],
                item[0]["id"],
            )
        )
        candidates.append(rows)

    def load(scene, row):
        scene_id = scene["id"]
        if scene_id in cache:
            crop, status, stats = cache[scene_id]
            row.update(stats, status=status)
            return crop
        if progress:
            progress(f"Checking clouds inside the region: {scene_id}…")
        stats = {}
        crop = None
        try:
            pad = math.ceil(request.policy.cloud_buffer_m / grid.resolution_m)
            padded = reader(scene, "scl", grid, padding=pad)
            expected = (grid.height + 2 * pad, grid.width + 2 * pad)
            if padded.shape != expected:
                raise SatelliteError("The quality layer did not cover the requested grid.")
            padded_aoi = np.pad(grid.aoi_mask, pad)
            usable, stats = assess_scl(padded, padded_aoi, request.policy, grid.resolution_m)
            usable = usable[pad : pad + grid.height, pad : pad + grid.width]
            scl = padded[pad : pad + grid.height, pad : pad + grid.width]
            if not quality_passes(stats, request.policy):
                status = "Region quality limits exceeded"
            else:
                rgb, rgb_valid, scaling = reflectance_rgb(scene, grid, reader)
                usable &= rgb_valid
                stats["usable_percent"] = float(100 * usable.sum() / grid.aoi_mask.sum())
                if not quality_passes(stats, request.policy):
                    status = "RGB missing-data coverage exceeds the limit"
                else:
                    crop = SceneCrop(scene, rgb, usable, scl, stats, scaling)
                    status = "Passed region checks"
        except (SatelliteError, KeyError, ValueError, TypeError) as error:
            status = f"Scene unavailable: {error}"
        cache[scene_id] = (crop, status, stats)
        row.update(stats, status=status)
        return crop

    for before_scene, before_row, before_time in candidates[0]:
        before = load(before_scene, before_row)
        if before is None:
            continue
        for after_scene, after_row, after_time in candidates[1]:
            # Require distinct calendar days, including when endpoint windows overlap.
            if before_time.date() >= after_time.date():
                continue
            after = load(after_scene, after_row)
            if after is None:
                continue
            valid = before.valid & after.valid
            joint = float(100 * valid.sum() / grid.aoi_mask.sum())
            if joint + 1e-9 < request.policy.min_usable_percent:
                continue
            before_row["status"], after_row["status"] = "Selected before", "Selected after"
            provenance = {
                "schema_version": "1.0",
                "provider": "Element 84 Earth Search",
                "collection": COLLECTION,
                "aoi": request.aoi,
                "grid": grid.metadata(),
                "requested_start": request.start.isoformat(),
                "requested_end": request.end.isoformat(),
                "search_windows": [[str(a), str(b)] for a, b in request.windows],
                "quality_policy": asdict(request.policy),
                "joint_usable_percent": joint,
                "rgb_mapping": {
                    "method": "linear reflectance to uint8",
                    "reflectance_min": 0.0,
                    "reflectance_max": DISPLAY_MAX_REFLECTANCE,
                    "per_scene_stretch": False,
                },
                "quality_note": "SCL is a 20 m classification, not a guarantee of cloud-free ground. Only classes 4, 5 and 6 are usable. Cloud/shadow exclusions use an additional square buffer. Inspect both images for missed cloud and haze.",
                "attribution": "Contains modified Copernicus Sentinel data. See scene acquisition years and provider licence.",
                "before": {
                    "scene_id": before_scene["id"],
                    "captured_utc": before_time.isoformat(),
                    "quality": before.quality,
                    "reflectance_scaling": before.scaling,
                },
                "after": {
                    "scene_id": after_scene["id"],
                    "captured_utc": after_time.isoformat(),
                    "quality": after.quality,
                    "reflectance_scaling": after.scaling,
                },
            }
            return SatellitePair(before, after, valid, grid, provenance, diagnostics)
    raise NoClearPair(
        "No qualifying pair was found near both dates. Try a wider endpoint window, a smaller region, or different dates. Quality limits were kept unchanged.",
        diagnostics,
    )
