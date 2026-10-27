import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import rasterio
import requests
from rasterio.transform import Affine
from shapely.geometry import box, mapping

from change_watch.analysis import analyze_pair
from change_watch.export import build_artifacts
from change_watch.satellite import (
    COLLECTION,
    CropGrid,
    EarthSearch,
    NoClearPair,
    QualityPolicy,
    SatelliteError,
    SatelliteRequest,
    assess_scl,
    find_pair,
    geotiff_bytes,
    make_grid,
    normalize_aoi,
    read_band,
)

AOI = mapping(box(69.25, 53.2, 69.27, 53.22))


def scene(name, day, cloud=0, geometry=AOI):
    return {
        "id": name,
        "collection": COLLECTION,
        "geometry": geometry,
        "properties": {"datetime": f"2025-06-{day:02d}T06:30:00Z", "eo:cloud_cover": cloud},
        "assets": {
            band: {
                "href": f"https://example.s3.us-west-2.amazonaws.com/{name}/{band}.tif",
                "raster:bands": [{"scale": 0.0001, "offset": -0.1, "nodata": 0}],
            }
            for band in ("scl", "red", "green", "blue")
        },
    }


class Catalogue:
    def __init__(self, items):
        self.items = items

    def search(self, aoi, start, end):
        return [
            item
            for item in self.items
            if start <= date.fromisoformat(item["properties"]["datetime"][:10]) <= end
        ]


def reader(item, band, grid, *, padding=0):
    size = (grid.height + 2 * padding, grid.width + 2 * padding)
    return np.full(size, 5 if band == "scl" else 2000, dtype=np.uint16)


class RegionAndDateTests(unittest.TestCase):
    def test_polygon_rejects_invalid_coordinates_and_unbounded_work(self):
        for value in (
            mapping(box(-180, -10, 180, 10)),
            mapping(box(69.0, 53.0, 69.9, 53.9)),
            {"type": "Point", "coordinates": [69, 53]},
            {
                "type": "Polygon",
                "coordinates": [[[69, 53], [70, 54], [69, 54], [70, 53], [69, 53]]],
            },
        ):
            with self.subTest(value=value), self.assertRaises(SatelliteError):
                make_grid(value)

    def test_grid_retains_polygon_instead_of_full_bounding_box(self):
        triangle = {
            "type": "Polygon",
            "coordinates": [[[69.25, 53.2], [69.27, 53.2], [69.25, 53.22], [69.25, 53.2]]],
        }
        grid = make_grid(triangle)
        self.assertGreater(grid.aoi_mask.sum(), 0)
        self.assertLess(grid.aoi_mask.sum(), grid.width * grid.height * 0.6)
        self.assertEqual(grid.crs, "EPSG:32642")
        self.assertEqual(grid.transform.a, 10)
        self.assertEqual(
            normalize_aoi({"type": "Feature", "properties": {}, "geometry": AOI}),
            normalize_aoi(AOI),
        )

    def test_windows_stay_inside_chosen_dates(self):
        request = SatelliteRequest(AOI, date(2025, 6, 1), date(2025, 6, 5), 14)
        self.assertEqual(
            request.windows, ((request.start, request.end), (request.start, request.end))
        )
        exact = SatelliteRequest(AOI, request.start, request.end, 0)
        self.assertEqual(
            exact.windows, ((request.start, request.start), (request.end, request.end))
        )
        self.assertNotEqual(request.key, exact.key)
        for start, end in (
            (request.end, request.start),
            (request.start, request.start),
            (date(2010, 1, 1), request.end),
            (request.start, date(2099, 1, 1)),
        ):
            with self.assertRaises(SatelliteError):
                SatelliteRequest(AOI, start, end)

    def test_policies_cannot_disable_coverage_or_accept_nonfinite_limits(self):
        for kwargs in (
            {"min_usable_percent": 0},
            {"max_aoi_cloud_percent": float("nan")},
            {"max_scene_cloud_percent": True},
            {"cloud_buffer_m": -1},
            {"cloud_buffer_m": 1.5},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(SatelliteError):
                QualityPolicy(**kwargs)


class CloudTests(unittest.TestCase):
    def test_every_unsuitable_scl_class_is_excluded(self):
        scl = np.arange(12, dtype=np.uint8).reshape(3, 4)
        valid, stats = assess_scl(scl, np.ones((3, 4), bool), QualityPolicy(cloud_buffer_m=0), 10)
        self.assertEqual(set(scl[valid]), {4, 5, 6})
        self.assertAlmostEqual(stats["usable_percent"], 25)
        self.assertAlmostEqual(stats["cloud_shadow_percent"], 100 / 3)

    def test_clouds_outside_polygon_do_not_count_without_buffer(self):
        scl = np.full((10, 10), 9, dtype=np.uint8)
        aoi = np.zeros((10, 10), bool)
        aoi[4:6, 4:6] = True
        scl[aoi] = 5
        valid, stats = assess_scl(scl, aoi, QualityPolicy(cloud_buffer_m=0), 10)
        self.assertEqual(valid.sum(), 4)
        self.assertEqual(stats["cloud_shadow_percent"], 0)
        valid, stats = assess_scl(scl, aoi, QualityPolicy(cloud_buffer_m=10), 10)
        self.assertFalse(valid.any())
        self.assertEqual(stats["cloud_shadow_percent"], 100)

    def request(self, policy=QualityPolicy(cloud_buffer_m=0)):
        return SatelliteRequest(AOI, date(2025, 6, 1), date(2025, 6, 30), 7, policy=policy)

    def test_low_scene_cloud_cannot_hide_cloud_over_the_selected_region(self):
        items = [scene("cloudy", 1), scene("clear", 3), scene("after", 30)]

        def cloudy_reader(item, band, grid, **kwargs):
            output = reader(item, band, grid, **kwargs)
            if item["id"] == "cloudy" and band == "scl":
                y, x = np.argwhere(grid.aoi_mask)[len(np.argwhere(grid.aoi_mask)) // 2]
                output[y, x] = 9
            return output

        pair = find_pair(self.request(), client=Catalogue(items), reader=cloudy_reader)
        self.assertEqual(pair.before.scene["id"], "clear")
        self.assertEqual(pair.after.scene["id"], "after")
        self.assertTrue(
            any(row["status"] == "Region quality limits exceeded" for row in pair.diagnostics)
        )

    def test_no_clear_pair_never_falls_back_to_cloudy_images(self):
        def cloudy_reader(item, band, grid, **kwargs):
            value = reader(item, band, grid, **kwargs)
            if band == "scl":
                value[:] = 8
            return value

        with self.assertRaises(NoClearPair) as caught:
            find_pair(
                self.request(),
                client=Catalogue([scene("before", 1), scene("after", 30)]),
                reader=cloudy_reader,
            )
        self.assertTrue(caught.exception.diagnostics)

    def test_missing_quality_and_rgb_nodata_fail_closed(self):
        for failed_band in ("scl", "red"):
            with self.subTest(failed_band=failed_band):

                def nodata(item, band, grid, **kwargs):
                    value = reader(item, band, grid, **kwargs)
                    if band == failed_band:
                        value[:] = 0
                    return value

                with self.assertRaises(NoClearPair):
                    find_pair(
                        self.request(),
                        client=Catalogue([scene("before", 1), scene("after", 30)]),
                        reader=nodata,
                    )

    def test_incomplete_footprint_and_high_scene_cloud_are_rejected(self):
        for bad in (
            scene("partial", 1, geometry=mapping(box(69.25, 53.2, 69.26, 53.21))),
            scene("cloudy", 1, cloud=30),
        ):
            with self.subTest(bad=bad["id"]), self.assertRaises(NoClearPair):
                find_pair(
                    self.request(), client=Catalogue([bad, scene("after", 30)]), reader=reader
                )

    def test_rejects_pair_with_insufficient_joint_coverage(self):
        def partial(item, band, grid, **kwargs):
            value = reader(item, band, grid, **kwargs)
            if band == "scl":
                indices = np.argwhere(grid.aoi_mask)
                amount = int(len(indices) * 0.04)
                part = indices[:amount] if item["id"] == "before" else indices[-amount:]
                value[part[:, 0], part[:, 1]] = 0
            return value

        with self.assertRaises(NoClearPair):
            find_pair(
                self.request(QualityPolicy(min_usable_percent=95, cloud_buffer_m=0)),
                client=Catalogue([scene("before", 1), scene("after", 30)]),
                reader=partial,
            )

    def test_overlapping_windows_require_different_days_and_order(self):
        request = SatelliteRequest(AOI, date(2025, 6, 1), date(2025, 6, 5), 14)
        with self.assertRaises(NoClearPair):
            find_pair(request, client=Catalogue([scene("only", 3)]), reader=reader)
        pair = find_pair(
            request, client=Catalogue([scene("early", 2), scene("late", 4)]), reader=reader
        )
        self.assertEqual(pair.before.scene["id"], "early")
        self.assertEqual(pair.after.scene["id"], "late")

    def test_cloud_buffer_reads_beyond_crop_boundary(self):
        def outside_cloud(item, band, grid, *, padding=0):
            value = reader(item, band, grid, padding=padding)
            if band == "scl":
                self.assertEqual(padding, 6)
                y, x = np.argwhere(grid.aoi_mask)[0]
                value[y + padding - 1, x + padding] = 9
            return value

        with self.assertRaises(NoClearPair):
            find_pair(
                self.request(QualityPolicy()),
                client=Catalogue([scene("before", 1), scene("after", 30)]),
                reader=outside_cloud,
            )


class CatalogueTests(unittest.TestCase):
    def response(self, body):
        value = Mock()
        value.json.return_value = body
        return value

    def test_paginates_without_dropping_early_scenes(self):
        session = Mock()
        session.get.side_effect = [
            self.response(
                {
                    "features": [scene("late", 30)],
                    "links": [
                        {
                            "rel": "next",
                            "href": "https://earth-search.aws.element84.com/v1/search?next=cursor",
                        }
                    ],
                }
            ),
            self.response({"features": [scene("early", 1)], "links": []}),
        ]
        rows = EarthSearch(session).search(AOI, date(2025, 6, 1), date(2025, 6, 30))
        self.assertEqual({row["id"] for row in rows}, {"late", "early"})
        self.assertIsNone(session.get.call_args.kwargs["params"])

    def test_refuses_truncation_instead_of_claiming_no_clear_image(self):
        session = Mock()
        session.get.return_value = self.response(
            {
                "features": [scene("one", 1)],
                "links": [
                    {
                        "rel": "next",
                        "href": "https://earth-search.aws.element84.com/v1/search?next=cursor",
                    }
                ],
            }
        )
        with self.assertRaisesRegex(SatelliteError, "Too many scenes"):
            EarthSearch(session, max_items=1).search(AOI, date(2025, 6, 1), date(2025, 6, 30))

    def test_connection_failure_does_not_appear_as_cloud_rejection(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()
        with self.assertRaisesRegex(SatelliteError, "Cannot reach"):
            EarthSearch(session).search(AOI, date(2025, 6, 1), date(2025, 6, 30))


class RasterAndExportTests(unittest.TestCase):
    def test_invalid_satellite_provenance_is_rejected_before_export(self):
        request = SatelliteRequest(AOI, date(2025, 6, 1), date(2025, 6, 30), 0)
        pair = find_pair(
            request,
            client=Catalogue([scene("before", 1), scene("after", 30)]),
            reader=reader,
        )
        for invalid in ("missing_geometry", "wrong_grid", "synthetic_source"):
            with self.subTest(invalid=invalid):
                provenance = json.loads(json.dumps(pair.provenance))
                if invalid == "missing_geometry":
                    del provenance["aoi"]
                elif invalid == "wrong_grid":
                    provenance["grid"]["width"] += 1
                with self.assertRaisesRegex(ValueError, "Satellite provenance"):
                    analyze_pair(
                        pair.before.rgb,
                        pair.after.rgb,
                        valid_mask=pair.valid,
                        acquisition=provenance,
                        synthetic=invalid == "synthetic_source",
                    )

    def test_different_source_grids_are_warped_to_exactly_the_same_crop(self):
        grid = CropGrid(
            "EPSG:32642",
            Affine(10, 0, 500020, 0, -10, 5900000),
            8,
            6,
            np.ones((6, 8), bool),
            10,
            0.01,
        )
        memories, paths = [], {}
        try:
            for name, offset in (("before", 0), ("after", 20)):
                memory = rasterio.io.MemoryFile()
                memories.append(memory)
                transform = Affine(10, 0, 500000 + offset, 0, -10, 5900020)
                ys, xs = np.indices((20, 20))
                values = (xs + offset // 10 + ys * 20 + 1).astype(np.uint16)
                with memory.open(
                    driver="GTiff",
                    width=20,
                    height=20,
                    count=1,
                    dtype="uint16",
                    crs=grid.crs,
                    transform=transform,
                    nodata=0,
                ) as target:
                    target.write(values, 1)
                paths[name] = memory.name
            with patch(
                "change_watch.satellite.asset_href",
                side_effect=lambda item, band: paths[item["id"]],
            ):
                before = read_band({"id": "before"}, "red", grid)
                after = read_band({"id": "after"}, "red", grid)
            np.testing.assert_array_equal(before, after)
            self.assertEqual(before.shape, (6, 8))
        finally:
            for memory in memories:
                memory.close()

    def test_satellite_bundle_retains_dates_georeferencing_and_offline_replay(self):
        request = SatelliteRequest(AOI, date(2025, 6, 1), date(2025, 6, 30), 0)
        pair = find_pair(
            request, client=Catalogue([scene("before", 1), scene("after", 30)]), reader=reader
        )
        self.assertEqual(pair.before.rgb.dtype, np.uint8)
        self.assertEqual(int(pair.before.rgb[tuple(np.argwhere(pair.grid.aoi_mask)[0])][0]), 85)
        analysis = analyze_pair(
            pair.before.rgb,
            pair.after.rgb,
            valid_mask=pair.valid,
            metadata=pair.metadata,
            acquisition=pair.provenance,
        )
        self.assertEqual(analysis.report["data_source"], "sentinel_2_collection_1")
        self.assertEqual(analysis.report["schema_version"], "1.2")
        artifacts = {
            **build_artifacts(analysis, pair.before.rgb, pair.after.rgb),
            **pair.artifacts(),
        }
        with rasterio.io.MemoryFile(artifacts["before_georeferenced.tif"]) as memory:
            with memory.open() as source:
                self.assertEqual(source.crs.to_string(), pair.grid.crs)
                self.assertEqual(source.transform, pair.grid.transform)
                np.testing.assert_array_equal(np.moveaxis(source.read(), 0, -1), pair.before.rgb)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in artifacts.items():
                (root / name).write_bytes(content)
            command = next(
                line
                for line in artifacts["REPRODUCE.txt"].decode().splitlines()
                if line.startswith("python -m")
            )
            result = subprocess.run(
                [sys.executable, *command.split()[1:]], cwd=root, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / "reproduced/report.json").read_text())
            self.assertEqual(report["run_id"], analysis.report["run_id"])
            self.assertEqual(report["acquisition"], pair.provenance)

    def test_mask_geotiff_roundtrip_preserves_zero_and_one(self):
        grid = make_grid(AOI)
        content = geotiff_bytes(grid.aoi_mask.astype(np.uint8), grid)
        with rasterio.io.MemoryFile(content) as memory:
            with memory.open() as source:
                np.testing.assert_array_equal(source.read(1), grid.aoi_mask.astype(np.uint8))


if __name__ == "__main__":
    unittest.main()
