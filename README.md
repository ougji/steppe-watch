# Steppe Watch

[![Python checks](https://github.com/ougji/steppe-watch/actions/workflows/ci.yml/badge.svg)](https://github.com/ougji/steppe-watch/actions/workflows/ci.yml)

A Python and Streamlit workbench for comparing satellite image crops and reviewing candidate land changes around mining sites in Kazakhstan.

**Status: v0.2 research prototype.** Compare aligned imagery, inspect individual regions, evaluate reference annotations and export a reproducible experiment. The default detector is the original RGB difference baseline; an optional median brightness-offset correction supports controlled comparisons. There is no trained model. Real-image accuracy has not been measured.

## What you can do

- Compare before/after imagery with an orange overlay, swipe view, score map and explicit pixel exclusions.
- Inspect ranked regions with local image crops, pixel bounding boxes, mean scores and CSV export.
- Upload reference masks and inspect precision, recall, F1, IoU, confusion counts and an error map.
- Compare nearby thresholds while holding the rest of the experiment fixed.
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

The app opens with a labelled synthetic demo. Choose **Upload images** to compare your own aligned 8-bit RGB PNG/JPEG crops, up to 4 million pixels and 25 MiB each. Optional grayscale usable/reference masks control exclusions and evaluation. The second demo scenario adds a brightness shift so you can inspect the experimental correction. No credentials or external imagery service is required. For runtime dependencies only, `python -m pip install -r requirements.txt` still works.

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

Omit `--valid-mask` if you have no usable-pixel mask. Optionally add `--truth reference_change_mask.png` to compute precision, recall, F1 and IoU against your reference annotations. White pixels indicate change; black indicates no change. Metrics with zero denominators are written as `null`, rather than claiming perfect performance.

Use a **new or empty output directory** for each run. Add `--metadata examples/metadata.json` to record source/site/dates, `--connectivity 8` to join diagonal neighbours, `--correction median_offset` for the experimental correction, and `--sensitivity --zip` for threshold comparisons and a portable bundle. After installation, `steppe-watch` is also available as a command.

Outputs retain `overlay.png`, `change_mask.png`, `difference.png` and `report.json`. They also include decoded before/after images, the usable/reference masks, `scores.npy`, `region_labels.npy`, `regions.csv`, `metadata.json` and `REPRODUCE.txt`. The label array preserves exact region shapes and links every retained pixel to its CSV region ID. Rerun commands preserve fractional thresholds at full precision. `--zip` adds `experiment.zip`. See the [artifact reference](docs/EXPERIMENTS.md#save-and-reproduce).

## Method

1. Accept two 8-bit RGB images on the same pixel grid. The tool rejects different dimensions; the user must establish geographic alignment separately.
2. Compute the mean absolute RGB difference at each usable pixel, using signed arithmetic to prevent integer overflow.
3. Flag pixels whose difference is strictly greater than the chosen threshold.
4. Group four-connected pixels and discard regions smaller than the minimum region size.
5. Report flagged pixels as a fraction of usable pixels. This is not an estimate of changed hectares or a probability of mining.

An RGB difference score is sensitive to illumination, seasons, shadows and registration errors. The optional median correction assumes most usable pixels are stable and may suppress real widespread change; it is not calibrated radiometric normalization. There is no automatic cloud detection, image registration or georeferencing. Use comparable imagery and exclude unsuitable pixels.

## Project structure

| Path | Responsibility |
| --- | --- |
| `app.py` | Streamlit review interface |
| `change_watch/core.py` | Detector, connected regions, sensitivity and evaluation |
| `change_watch/analysis.py` | Shared pipeline, metadata, input fingerprints and reports |
| `change_watch/io.py` | Consistent bounded image decoding |
| `change_watch/export.py` | Reproducible artifacts and ZIP bundles |
| `change_watch/__main__.py` | Installable CLI |
| `tests/` | Numerical, input, CLI, export and Streamlit interaction tests |

GitHub Actions runs tests and lint/format checks on Windows and Linux with Python 3.10 and 3.12, and saves a demo experiment artifact. Root `core.py` and `demo.py` preserve old imports while delegating to the package.

## Evaluation status

The generated image pair includes an exact reference change mask. Tests check that the pipeline recovers this deliberately simple synthetic change. Synthetic scores do not estimate accuracy on real imagery.

The Kokshetau screenshots provide a preliminary real-image example. Detection accuracy on real imagery has not been measured yet, because reference annotations are not included. The reported flagged-pixel percentages are outputs of the baseline, not accuracy metrics.

For future ML experiments, document the image source, acquisition dates, location, processing, labels and train/validation/test separation. Evaluate on separate sites or independent image pairs rather than randomly splitting neighboring pixels or overlapping patches from the same pair.

## Next milestone

1. Add the original Kokshetau image pair, acquisition dates, location, source and processing details to make the experiment reproducible.
2. Inspect image alignment and exclude clouds, shadows and missing data.
3. Create reference annotations and evaluate the baseline using precision, recall, F1 and IoU.
4. Collect additional image pairs, train a small ML model and compare it with the baseline on held-out data.

See [ROADMAP.md](ROADMAP.md) for the October delivery plan and [CONTRIBUTIONS.md](CONTRIBUTIONS.md) for how to keep the technical work explainable.

## References

- [NumPy subtraction](https://numpy.org/doc/stable/reference/generated/numpy.subtract.html)
- [SciPy connected-component labelling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.label.html)
- [Streamlit file uploads](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)

## Contributions

The initial scaffold was developed with assistance from ChatGPT/Codex. Personal contributions and experiment notes are recorded in [CONTRIBUTIONS.md](CONTRIBUTIONS.md).
