# Your first session

Goal: run the workbench, inspect a candidate region and reproduce an experiment.

## 1. Install and open

From the repository folder with Python 3.10 or newer:

```bash
python -m venv .venv
```

Windows PowerShell: `.venv\Scripts\Activate.ps1`

macOS/Linux: `source .venv/bin/activate`

```bash
python -m pip install -e ".[dev]"
python -m streamlit run app.py
```

Open the local URL printed in the terminal. The app starts with generated terrain, not real satellite observations.

## 2. Inspect the result

1. Open **Compare imagery** and compare the before, after and orange overlay. Expand the swipe view.
2. Open **Inspect regions** to see the largest region's image crop and pixel measurements.
3. Open **Evaluate & tune** to compare the synthetic reference. Perfect synthetic scores only check this deliberately simple example.
4. Set the threshold to 255. No pixel can pass the strict greater-than test. Restore it to 35.
5. Choose **Expansion + brightness shift**, then enable **Correct global brightness offset**. Explain why this helps the synthetic scenario and why its stable-majority assumption may fail on real imagery.
6. Enable **Compare nearby thresholds** and inspect the sensitivity curve. It is not an accuracy curve.

## 3. Save and rerun

In **Export experiment**, prepare and download the ZIP. Extract it and inspect `report.json`, `regions.csv` and `REPRODUCE.txt`. The bundle includes its input images, so check image rights before sharing a real experiment.

Or use the CLI:

```bash
python -m change_watch --demo --sensitivity --zip --out outputs/first-demo
```

Choose a new output folder for subsequent runs. Existing experiments are preserved.

## 4. Check the software

```bash
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
```

The test suite covers the original baseline, masks, region statistics, correction, image validation, exported results, command-line errors and app interactions.

## 5. Bring your own imagery

Prepare two aligned 8-bit RGB PNG/JPEG crops. Choose **Upload images**, add exclusions/reference annotations if available, and record provenance. Keep unlabelled pixels out of evaluation using the usable mask. Follow [the experiment guide](docs/EXPERIMENTS.md) and complete [DATA_NOTES.md](DATA_NOTES.md).

A useful next contribution is a permitted image pair with documented source/dates, checked alignment and independent annotations. Record the result and your own review in [CONTRIBUTIONS.md](CONTRIBUTIONS.md).
