# Running a defensible comparison

## Prepare the pair

Use two permitted 8-bit RGB PNG/JPEG crops on the same pixel grid. Record the source, acquisition dates, bands, resolution, processing and license. Equal dimensions do not prove alignment. Compare stable features such as road intersections before analyzing the pair; Steppe Watch does not register images or read geographic coordinates.

The app and CLI accept at most 4 million pixels and 25 MiB per image. EXIF orientation is applied consistently. Transparency, high-bit-depth images and coloured masks are rejected instead of being silently interpreted. Prepare radiometrically suitable RGB crops from original satellite products separately.

Create a grayscale usable mask: values above 127 are usable on **both** dates. Exclude clouds, shadows and missing data. For evaluation on partial annotations, also exclude unlabelled/uncertain pixels. A black reference pixel means known unchanged, not unknown. An all-excluded mask is an error.

## Start with the baseline

The default score is the mean absolute RGB difference. Pixels must be **strictly greater** than the threshold. The default region filter retains four-connected components with at least 25 pixels. Eight-connectivity optionally joins diagonal pixels. Region IDs follow the retained components in scan order; the table sorts them by descending size. IDs are only meaningful within the current run.

The reported fraction is retained flagged pixels divided by usable pixels. It is not an accuracy estimate, an area in hectares or a probability. Region bounding boxes use zero-based pixel coordinates with exclusive right/bottom edges. The region inspector crops with context; the orange overlay highlights the selected component only.

## Compare the experimental brightness correction

`--correction median_offset` estimates a signed median difference for each RGB channel across usable pixels. It subtracts that offset before taking the absolute mean difference. Residual scores are capped at 255 so controls retain the original score scale. The report records the three offsets and the raw mean difference.

This assumes most usable pixels are stable. It can remove a uniform exposure shift, but can also suppress genuine widespread change; it is not calibrated radiometric normalization. Clipping/saturation, seasonality and local illumination remain problems. Always compare with `--correction none` using the same exclusions and annotations.

The app's second synthetic scenario adds a uniform +45 RGB offset to the generated after image, with clipping at 255. It exists to exercise this specific failure mode. Both scenarios are illustrations, not evidence of performance on satellite imagery.

## Evaluate and tune separately

Supply a grayscale reference mask with white for annotated change and black for annotated stable areas. Precision, recall, F1 and IoU are computed only on usable pixels. Undefined ratios are JSON `null` / “Undefined” in the app. Inspect the error map: green true positives, orange false positives, blue misses and slate exclusions.

`--sensitivity` computes the current threshold, ±10, ±20 and the 0/255 endpoints (deduplicated and clipped). It reuses the score and holds other settings fixed. The curve shows sensitivity, not an automatic optimum. Do not tune parameters on a held-out evaluation set. Separate sites or independent image pairs are better evaluation units than adjacent pixels.

## Save and reproduce

```bash
python -m change_watch --before before.png --after after.png --valid-mask usable.png --truth reference.png --metadata examples/metadata.json --threshold 35 --min-pixels 25 --sensitivity --zip --out outputs/pilot-baseline
```

Use a new or empty output directory for each run; previous results are never silently overwritten. The app's **Export experiment** tab provides the same artifacts. After changing inputs/settings, prepare the bundle again before downloading.

| Artifact | Meaning |
| --- | --- |
| `before.png`, `after.png` | Exact decoded, EXIF-oriented RGB inputs |
| `usable_mask.png` | White usable, black excluded |
| `reference_mask.png` | Optional supplied/generated reference |
| `change_mask.png` | Retained flagged pixels |
| `overlay.png` | After image with orange candidates |
| `difference.png` | Truncated 8-bit score preview; excluded pixels are zero |
| `scores.npy` | Full-precision score array; load with `allow_pickle=False` |
| `regions.csv` | All region IDs, pixel counts, mean scores and bounding boxes |
| `report.json` | Schema version, settings, counts, provenance, regions, evaluation and warnings |
| `metadata.json` | Site, source, dates and notes |
| `REPRODUCE.txt` | Command to rerun the exported inputs |

Reports retain the v0.1 summary keys at the top level. `schema_version` describes the report format; `software_version` identifies Steppe Watch. Input SHA-256 values hash decoded array dtype, shape and contiguous pixel bytes, **not original compressed files**. The run ID derives from these fingerprints, settings, software version, metadata, source kind and sensitivity option. Creation timestamps are UTC and do not affect run IDs.

Extract the ZIP, install the matching project version, and run the command in `REPRODUCE.txt`. Exported synthetic inputs replay through the upload/CLI path and are therefore labelled user-supplied; counts, masks and scores remain reproducible, while provenance labels, run IDs and timestamps can differ. Keep the original report for the synthetic label. The bundle contains images: check redistribution rights before sharing it.

## What is still missing

The Kokshetau screenshots remain a preliminary example. Original imagery, acquisition dates and reference annotations have not been added by this upgrade. No real-data accuracy claim, automatic cloud detection, georeferencing, hectares calculation, image registration or trained model is implemented. A documented, independently reproducible real-image experiment is the next research milestone.
