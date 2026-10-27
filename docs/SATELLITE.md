# Select a region and compare dates

## Open the map

Install the current dependencies with `python -m pip install -e ".[dev]"`, then run `python -m streamlit run app.py`.

**Satellite map** is the default image source. The map opens near Kokshetau. Use **Move the map or enter exact bounds** to navigate with latitude/longitude or specify west/south/east/north bounds. Satellite and OpenStreetMap basemaps are available in the layer control. They locate the site; their imagery is unrelated to the comparison dates.

Draw a rectangle or polygon using the tools on the map's left edge. A new drawing replaces the previous one. Use the edit tool to change its outline, or **Clear region** to remove it. The crop must be 0.01–400 km², fit within 4 million output pixels, and lie between 80°S and 84°N. A long or narrow polygon's bounding crop must also fit the pixel budget. Date-line-crossing and multiple polygons are not supported.

The app uses the exact polygon for quality measurements and detection, with pixel centres determining inclusion. Pixels outside the polygon are black in the cropped inputs and excluded from detection. The general **Usable bounding crop** metric uses the surrounding rectangle; the acquisition table's region coverage uses only the polygon.

## Pick start and end dates

Choose dates between 2017 and today, with start earlier than end. Sentinel-2 is not guaranteed to observe the location on a specific day. **Search near each endpoint** offers:

| Window | Before candidates | After candidates |
| --- | --- | --- |
| Exact dates only | Start date | End date |
| Up to N days inward | Start through start + N days | End − N days through end |

Both windows are clipped to the overall chosen interval. Start-side candidates are checked from earliest to latest; end-side candidates from latest to earliest, with lower scene cloud as the same-day tie break. The first pair passing all checks is used. Both observations must be on different UTC dates and before must precede after, including when the endpoint windows overlap. The actual capture dates and timestamps appear above the comparison; requested dates are not represented as actual observations.

## Check that the region is clear

Click **Find clear imagery & compare**. This reads public Sentinel-2 Collection 1 Level-2A data from Earth Search. No API key, Earth Engine account or paid subscription is required. An internet connection to the catalogue and its public AWS raster assets is required; map tiles and drawing scripts also require their respective hosts.

The default quality policy requires:

1. At most 20% cloud cover across the full scene, based on `eo:cloud_cover` metadata.
2. A scene footprint covering the entire polygon. This version does not mosaic adjacent tiles.
3. Zero detected cloud/shadow over the selected polygon, including a 60 m square buffer around SCL cloud, cirrus and cloud-shadow pixels. The quality read extends beyond the crop so nearby clouds are considered.
4. 100% usable region coverage on each date and in their intersection. RGB nodata is checked after SCL screening.

Only SCL classes 4 (vegetation), 5 (non-vegetated land) and 6 (water) are usable. Cloud shadow (3), medium/high cloud (8/9), cirrus (10), snow (11), dark/cast-shadow (2), unclassified (7), defective (1), nodata (0) and unknown values are excluded. The native SCL resolution is 20 m even on a 10 m comparison grid. Small clouds, haze and classification mistakes can escape the check; inspect both images.

If the whole-region requirement is disabled, explicit sliders control allowed region cloud/shadow and minimum joint usable coverage. Excluded pixels still cannot become changes. The app never changes these limits by itself.

If no pair qualifies, it reports that outcome and lists scene rejection reasons. Widen the endpoint windows, use different dates or choose a smaller region. Summer-to-summer comparisons can reduce seasonal differences in northern Kazakhstan. Increasing the scene-wide cloud cap can allow a locally clear crop from a cloudier tile while keeping strict region checks. A partial tile needs a smaller crop; this version cannot fill it from another scene.

The search follows catalogue pagination and refuses incomplete searches over its 200-item limit per endpoint window. Shorten the window or reduce the region if this limit is reached. Network or asset failures do not pass as clear imagery.

## Compare and export

Both RGB crops and SCL masks are resampled with nearest-neighbour onto the same UTM grid. RGB bands are converted from Collection 1 digital numbers using their recorded scale/offset, then linearly mapped from reflectance 0–0.3 to 8-bit RGB. This fixed mapping avoids independent scene stretches. Values outside the display range are clipped; this remains an RGB visual-change baseline, not a calibrated spectral detector. Geographic alignment does not remove all sensor registration errors.

Use the existing overlay, swipe, regions and threshold tools. Changing a region, date, window, resolution or quality setting invalidates the loaded imagery until a new acquisition succeeds. Changing detector settings reuses the already downloaded pair.

The experiment ZIP retains the existing PNG inputs, masks, scores, region IDs, report and replay command. Satellite comparisons also add:

| File | Contents |
| --- | --- |
| `aoi.geojson` | Selected WGS84 polygon |
| `satellite_provenance.json` | Requested dates, actual dates, scene IDs, policy, quality measurements, grid and RGB scaling |
| `before_scene.json`, `after_scene.json` | Original STAC item metadata and asset URLs |
| `before_scl.tif`, `after_scl.tif` | SCL crops on the common grid; nodata and outside-polygon areas require the usable mask |
| `before_georeferenced.tif`, `after_georeferenced.tif` | Cropped 8-bit RGB with CRS and transform |
| `change_mask_georeferenced.tif` | 0/1 retained change mask with CRS and transform |
| `usable_mask_georeferenced.tif` | 0/1 joint usable mask with CRS and transform |

The exported replay command uses `--acquisition satellite_provenance.json` to preserve satellite provenance and the run identity without downloading imagery again. Masks distinguish excluded pixels from stable land; a zero change value alone does not establish either.

## Sources

- [Earth Search Collection 1 catalogue](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a)
- [Earth Search project and collection updates](https://github.com/Element84/earth-search)
- [Copernicus scene classification and processing](https://sentiwiki.copernicus.eu/web/s2-processing)
- [Rasterio virtual warping](https://rasterio.readthedocs.io/en/stable/topics/virtual-warping.html)

## Live acquisition smoke check

On 2026-10-28, the acquisition and export pipeline was exercised with real public imagery near Kokshetau:

- WGS84 bounds: west `69.25348163`, south `53.20638266`, east `69.25648680`, north `53.20818687` (about 0.0403 km²).
- Before: `S2A_T42UWD_20250610T064320_L2A`, captured 2025-06-10.
- After: `S2C_T42UWD_20250824T063150_L2A`, captured 2025-08-24.
- Exact-date search, 10 m common UTM grid, default 60 m extra cloud buffer and strict quality policy. The selected polygon had 100% jointly usable pixels and 0% buffered cloud/shadow on both dates.
- RGB band crops, scene classification, provenance, report and georeferenced exports were produced. A larger nearby crop was rejected for unclassified pixels even though its scene-wide cloud percentage was low.

This checks live acquisition and quality gating, not whether the detector identifies real land changes. The crop was selected for clear coverage; it is not an annotated mining evaluation dataset. Raster assets and catalogue contents can change, so later retrieval may differ.

Cloud screening and crop alignment do not validate real-world detection accuracy. Use independent reference annotations before reporting precision, recall or IoU.
