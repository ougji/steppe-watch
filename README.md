# Steppe Watch

[![Python checks](https://github.com/ougji/steppe-watch/actions/workflows/ci.yml/badge.svg)](https://github.com/ougji/steppe-watch/actions/workflows/ci.yml)

A Python and Streamlit workbench for comparing satellite image crops and reviewing candidate land changes around mining sites in Kazakhstan.

**Status: v0.4 research prototype.** Draw a region on a map, pick start/end dates and acquire a cloud-screened Sentinel-2 pair on a shared geographic grid. Compare changes, inspect individual regions, evaluate reference annotations, benchmark multiple pairs and export a reproducible experiment. The detector remains an RGB difference baseline; there is no trained model. Real-image detection accuracy has not been measured.

## What you can do

- Draw and edit a rectangle or polygon on a satellite/street map, or enter exact geographic bounds.
- Choose start/end dates using calendars; search exact dates or up to 30 days inward from each endpoint without leaving the requested interval.
- Acquire public Sentinel-2 Collection 1 L2A crops without API keys. Screen scene-wide cloud metadata, then inspect SCL clouds, shadows, snow, missing data and usable coverage inside the exact region.
- Default to **0% detected cloud/shadow and 100% usable region coverage**, with an extra 60 m cloud/shadow buffer. No qualifying pair means no comparison; limits are never relaxed automatically.
- Align both acquisitions on one 10 m or 20 m UTM grid and retain actual capture dates, scene IDs, quality checks, region GeoJSON and georeferenced TIFFs in the experiment ZIP.
- Compare before/after imagery with an orange overlay, swipe view, score map and explicit pixel exclusions.
- Inspect ranked regions with local image crops, pixel bounding boxes, mean scores and CSV export.
- Upload reference masks and inspect precision, recall, F1, IoU, confusion counts and an error map.
- Evaluate partially annotated crops with a separate annotation coverage mask, preserving detection across all usable pixels.
- Compare nearby thresholds while holding the rest of the experiment fixed.
- Benchmark multiple annotated image pairs under fixed settings, comparing baseline and brightness correction with pooled and per-pair metrics.
- Record imagery provenance and export a ZIP with inputs, masks, full-precision scores, a versioned report and a rerun command.
- Run the same pipeline from the CLI or Python, with shared input checks and automated tests.

Start with the [quick start](#run), [first-session walkthrough](START_HERE.md) or [experiment guide](docs/EXPERIMENTS.md). Changes are recorded in [CHANGELOG.md](CHANGELOG.md).

## Preliminary experiment near Kokshetau

Two satellite images of a mining site near Kokshetau, Kazakhstan, were compared at two difference thresholds. The minimum region size was kept at **25 pixels** for both runs. The results below were recorded from the application screenshots.

| Difference threshold | Minimum region size | Flagged pixels | Usable pixels flagged | Candidate regions |
| --- | --- | --- | --- | --- |
| 35 | 25 pixels | 78,860 | 10.8% | 75 |
| 41 | 25 pixels | 46,137 | 6.3% | 59 |

### Threshold 35

![Kokshetau image comparison at threshold 35, with 10.8% of usable pixels flagged](<threshold-35 (1).png>)

### Threshold 41

![Kokshetau image comparison at threshold 41, with 6.3% of usable pixels flagged](threshold-41.png)

Increasing the threshold reduced the number of flagged pixels. This demonstrates sensitivity to the threshold; it does not establish which setting is more accurate. Reference annotations are needed to distinguish actual land changes from effects such as illumination, vegetation, shadows or alignment differences.

**These percentages describe flagged pixels, not detection accuracy or the percentage of the mine that expanded.** Candidate regions are connected groups of flagged pixels, not a count of mines.

The original input images, acquisition dates and geographic metadata are not yet included with this example. The screenshots document the preliminary runs, but do not make this real-data experiment independently reproducible yet.

## Synthetic demonstration

![Synthetic demonstration: before, after and flagged changes](examples/synthetic_preview.png)

The illustration above is generated data. It depicts an artificial quarry-shaped expansion to demonstrate the pipeline; it is not a real mine or a satellite image.

## Run

Python 3.10 or newer:

```bash
python -m venv .venv
```

Activate the environment on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and open the app:

```bash
python -m pip install -e ".[dev]"
python -m streamlit run app.py
```

The app opens in **Satellite map** mode. Draw a crop, select the two dates and click **Find clear imagery & compare**. Satellite access needs an internet connection, but no account, API key or paid imagery subscription. See the [satellite workflow](docs/SATELLITE.md) for date selection, cloud checks, limits and troubleshooting.

Choose **Synthetic demo** for an offline generated example, or **Upload images** for your own aligned 8-bit RGB PNG/JPEG crops, up to 4 million pixels and 25 MiB each. Optional grayscale usable/reference masks control exclusions and evaluation. The second demo scenario adds a brightness shift so you can inspect the experimental correction. For runtime dependencies only, `python -m pip install -r requirements.txt` still works.

## Reproduce a comparison without the interface

```bash
python -m change_watch --demo --sensitivity --zip --out outputs/demo
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
```

For your own images:

```bash
python -m change_watch --before before.png --after after.png --valid-mask usable.png --threshold 35 --min-pixels 25 --out outputs/site
```

Omit `--valid-mask` if you have no usable-pixel mask. Optionally add `--truth reference_change_mask.png` to compute precision, recall, F1 and IoU against your reference annotations. White pixels indicate change; black indicates no change. For partial annotations, add `--evaluation-mask annotated.png`: white marks known labels and black marks unknown areas. Evaluation uses annotated usable pixels; detection still uses every usable pixel. Metrics with zero denominators are written as `null`.

Use a **new or empty output directory** for each run. Add `--metadata examples/metadata.json` to record source/site/dates, `--connectivity 8` to join diagonal neighbours, `--correction median_offset` for the experimental correction, and `--sensitivity --zip` for threshold comparisons and a portable bundle. After installation, `steppe-watch` is also available as a command.

Outputs retain `overlay.png`, `change_mask.png`, `difference.png` and `report.json`. They also include decoded before/after images, the usable/reference masks, `scores.npy`, `region_labels.npy`, `regions.csv`, `metadata.json` and `REPRODUCE.txt`. The label array preserves exact region shapes and links every retained pixel to its CSV region ID. Rerun commands preserve fractional thresholds at full precision. `--zip` adds `experiment.zip`. See the [artifact reference](docs/EXPERIMENTS.md#save-and-reproduce).

## Evaluate multiple pairs

```bash
python -m change_watch.benchmark examples/benchmark.json --out outputs/benchmark
```

This runs the baseline and brightness correction on two labelled synthetic scenarios, saving `benchmark.json` and `cases.csv`. Paths are relative to the manifest, so it also works from another directory. Copy the manifest for your own annotated pairs; use independent held-out examples for accuracy estimates. See [the benchmark guide](docs/BENCHMARKS.md) for the schema, aggregation rules and synthetic results.

## Method

1. Acquire Sentinel-2 crops on a common projected grid, or accept two aligned 8-bit RGB uploads. Uploaded imagery still requires a separate geographic alignment check.
2. Compute the mean absolute RGB difference at each usable pixel, using signed arithmetic to prevent integer overflow.
3. Flag pixels whose difference is strictly greater than the chosen threshold.
4. Group four-connected pixels and discard regions smaller than the minimum region size.
5. Report flagged pixels as a fraction of usable pixels. This is not an estimate of changed hectares or a probability of mining.

An RGB difference score is sensitive to illumination, seasons, shadows and registration errors. The optional median correction assumes most usable pixels are stable and may suppress real widespread change; it is not calibrated radiometric normalization. Satellite mode uses the provider's 20 m scene classification for automatic exclusions and geographic reprojection for a shared grid; it does not estimate subpixel image registration. Cloud classification can miss thin/small clouds and haze. Upload mode relies on your alignment and exclusion masks.

## Project structure

| Path | Responsibility |
| --- | --- |
| `app.py` | Streamlit review interface |
| `change_watch/core.py` | Detector, connected regions, sensitivity and evaluation |
| `change_watch/analysis.py` | Shared pipeline, metadata, input fingerprints and reports |
| `change_watch/io.py` | Consistent bounded image decoding |
| `change_watch/export.py` | Reproducible artifacts and ZIP bundles |
| `change_watch/__main__.py` | Installable CLI |
| `change_watch/benchmark.py` | Dataset manifests, fixed-setting comparisons and aggregate metrics |
| `change_watch/satellite.py` | Bounded STAC search, polygon crops, SCL screening, shared grid and satellite provenance |
| `change_watch/satellite_ui.py` | Editable map, calendar inputs, quality settings and acquisition state |
| `tests/` | Numerical, input, CLI, export and Streamlit interaction tests |

GitHub Actions runs tests and lint/format checks on Windows and Linux with Python 3.10 and 3.12, and saves a demo experiment artifact. Root `core.py` and `demo.py` preserve old imports while delegating to the package.

## Evaluation status

The generated image pair includes an exact reference change mask. Tests check that the pipeline recovers this deliberately simple synthetic change. Synthetic scores do not estimate accuracy on real imagery.

The Kokshetau screenshots provide a preliminary real-image example. Detection accuracy on real imagery has not been measured yet, because reference annotations are not included. The reported flagged-pixel percentages are outputs of the baseline, not accuracy metrics.

For future ML experiments, document the image source, acquisition dates, location, processing, labels and train/validation/test separation. Evaluate on separate sites or independent image pairs rather than randomly splitting neighboring pixels or overlapping patches from the same pair.

## Next milestone

1. Use the satellite workflow to document a new reproducible Kokshetau experiment; the old screenshots still lack their original inputs.
2. Inspect residual alignment and any clouds or haze missed by the provider's classification.
3. Create reference annotations and evaluate the baseline using precision, recall, F1 and IoU.
4. Collect additional image pairs, train a small ML model and compare it with the baseline on held-out data.

See [ROADMAP.md](ROADMAP.md) for the October delivery plan and [CONTRIBUTIONS.md](CONTRIBUTIONS.md) for how to keep the technical work explainable.

## References

- [NumPy subtraction](https://numpy.org/doc/stable/reference/generated/numpy.subtract.html)
- [SciPy connected-component labelling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.label.html)
- [Streamlit file uploads](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)
- [Element 84 Earth Search catalogue](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a)
- [Sentinel-2 scene classification](https://sentiwiki.copernicus.eu/web/s2-processing)
- [Rasterio virtual warping](https://rasterio.readthedocs.io/en/stable/topics/virtual-warping.html)

## Contributions

The initial scaffold was developed with assistance from ChatGPT/Codex. Personal contributions and experiment notes are recorded in [CONTRIBUTIONS.md](CONTRIBUTIONS.md).
