# Changelog

## Unreleased

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
