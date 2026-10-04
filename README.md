# Steppe Watch

A small, reproducible image comparison tool for a future Kazakhstan mining-monitoring project.

**Status: v0.1 prototype.** Compare two aligned RGB images, highlight candidate visual changes, and export a mask and a JSON report. This version is a classical difference baseline. It does not contain a trained ML model, verified satellite observations, a mining classifier, or a legal determination system.

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
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app opens with a labelled synthetic demo. Choose **Upload images** to compare your own aligned RGB PNG/JPEG crops. An optional white/black usable-pixel mask excludes clouds, shadows, or missing imagery that you have identified on either date.

## Reproduce a comparison without the interface

```bash
python -m change_watch --demo --out outputs/demo
python -m unittest discover -s tests -v
```

For your own images:

```bash
python -m change_watch --before before.png --after after.png --valid-mask usable.png --threshold 35 --min-pixels 25 --out outputs/site
```

Omit `--valid-mask` if you have no usable-pixel mask. Optionally add `--truth reference_change_mask.png` to compute precision, recall, F1 and IoU against your reference annotations. White pixels indicate change; black indicates no change. Metrics with zero denominators are written as `null`, rather than claiming perfect performance.

Outputs: `overlay.png`, `change_mask.png`, `difference.png`, `report.json`.

## Method

1. Accept two 8-bit RGB images on the same pixel grid. The tool rejects different dimensions; the user must establish geographic alignment separately.
2. Compute the mean absolute RGB difference at each usable pixel, using signed arithmetic to prevent integer overflow.
3. Flag pixels whose difference is strictly greater than the chosen threshold.
4. Group four-connected pixels and discard regions smaller than the minimum region size.
5. Report flagged pixels as a fraction of usable pixels. This is not an estimate of changed hectares or a probability of mining.

An RGB difference score is sensitive to illumination, seasons, shadows and registration errors. There is no automatic cloud detection, image registration, georeferencing, or radiometric correction yet. Use comparable imagery and exclude unsuitable pixels. Real satellite work will need those additional controls.

## Evaluation status

The generated image pair includes an exact reference change mask. Tests check that the pipeline recovers this deliberately simple synthetic change. Synthetic scores do not estimate accuracy on real imagery.

No real-world results are available yet. Before adding an ML claim, record the image source, acquisition dates, location, processing, labels, train/validation/test separation, and baseline comparison. Never randomly split overlapping image patches from the same site and call that independent evaluation.

## Next milestone

Select one real pilot location. Obtain comparable, permitted imagery from two dates, document its provenance, mask clouds and shadows, inspect alignment, and annotate candidate changes. Run the baseline and inspect false positives before deciding whether a learned model is useful.

See [ROADMAP.md](ROADMAP.md) for the October delivery plan and [CONTRIBUTIONS.md](CONTRIBUTIONS.md) for how to keep the technical work explainable.

## References

- [NumPy subtraction](https://numpy.org/doc/stable/reference/generated/numpy.subtract.html)
- [SciPy connected-component labelling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.label.html)
- [Streamlit file uploads](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)

## Start a GitHub repository

Create an empty repository named `steppe-watch` on GitHub. Do not initialize it with another README. From this project folder:

```bash
git init
git add .
git commit -m "Add reproducible RGB change detection baseline"
git branch -M main
```

Then run `git remote add origin` with the exact repository URL GitHub gives you, followed by `git push -u origin main`. Authenticate through GitHub's normal sign-in flow. Keep credentials out of source files.
