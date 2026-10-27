# Changelog

## 0.4.0 — 2026-10-28

- Add an editable rectangle/polygon map, satellite and street basemaps, coordinate navigation, exact bounds and region GeoJSON download.
- Add start/end calendars and bounded endpoint windows, showing actual acquisition timestamps and keeping every scene inside the requested interval.
- Acquire public Sentinel-2 Collection 1 L2A COG crops through paginated Earth Search without credentials; resample both dates onto one 10 m or 20 m UTM grid.
- Screen scene-wide cloud cover and crop-level SCL cloud, shadow, cirrus, snow, unknown and missing pixels. Default to zero detected cloud/shadow and full usable region coverage, with a configurable 60 m safety buffer and joint-date coverage checks. Never silently relax the limits.
- Reuse the RGB detector with one fixed reflectance mapping and consistent per-band scale/offset handling. Invalidate imagery when region, dates or quality settings change.
- Add satellite provenance to report schema 1.2 and the reproducible run identity; export scene metadata, region GeoJSON, quality layers and georeferenced RGB/change/usable TIFFs. Retain provenance in offline CLI replay.
- Add cloud, nodata, pagination, date, grid alignment, replay and satellite interface regression tests. Keep synthetic demonstrations and upload workflows.

## 0.3.0 — 2026-10-19

- Add manifest-driven batch evaluation with per-pair JSON/CSV results, pooled pixel metrics, macro averages and explicit counts of defined metrics; include a runnable two-scenario synthetic benchmark.

- Separate annotation coverage from usable-pixel exclusions in Python, CLI and app; report evaluated coverage and preserve it in exported experiments (report schema 1.1).

- Preserve fractional thresholds in exported rerun commands, fixing different masks at score boundaries.
- Export `region_labels.npy` so exact region shapes can be matched to the CSV without rerunning detection.
- Repair the threshold-35 screenshot link.

## 0.2.0 — 2026-10-14

- Rebuilt the Streamlit interface around comparison, region review, evaluation and export workflows, with a responsive theme and a before/after swipe.
- Added region IDs, bounding boxes, size ranking, local crops and CSV exports; optional eight-connectivity preserves the four-connected default.
- Added experimental median RGB offset correction and a synthetic brightness-shift scenario. The original baseline remains the default.
- Added reference-mask upload, error maps, confusion counts and optional threshold sensitivity analysis.
- Unified CLI/app analysis, validation and artifact generation. Added provenance fields, decoded-input hashes, run IDs and versioned reports.
- Added reproducible ZIP bundles including decoded inputs, full-precision scores and rerun instructions. The CLI preserves existing experiments by requiring a new/empty destination.
- Added installable package/CLI, Windows/Linux CI, lint/format checks and expanded numerical, input, CLI, export and UI tests.
- Replaced duplicate root implementations with compatibility imports and removed tracked Python bytecode.

Real-data evaluation remains pending. This release improves tooling and synthetic verification; it does not establish satellite detection accuracy.
