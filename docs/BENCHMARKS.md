# Evaluate a collection of image pairs

Use a manifest to compare the RGB baseline (`none`) and optional median correction (`median_offset`) with one threshold, minimum region size and connectivity across all pairs. The runner reports every result; it does not select parameters or a winning method.

## Run the included pipeline check

From the repository directory after installing the project:

```bash
python -m change_watch.benchmark examples/benchmark.json --out outputs/benchmark
```

Use a new or empty output directory. Files are written only after every case has completed successfully. A missing image or invalid mask stops the run with its case ID; cases are never silently skipped. Existing output is preserved.

The two generated scenarios have these results with threshold 35, minimum region size 25 and four-connectivity:

| Correction | Pooled precision | Pooled recall | Pooled F1 | Pooled IoU | Mean per-pair IoU |
| --- | ---: | ---: | ---: | ---: | ---: |
| `none` | 0.1409 | 1.0000 | 0.2470 | 0.1409 | 0.5379 |
| `median_offset` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

These are artificial expansion and exposure-shift scenarios derived from the same scene. They check known code behavior, not independent sites or satellite accuracy. The correction can hide widespread genuine change; tests explicitly include that failure case. Real-data evaluation remains pending.

## Prepare a manifest

```json
{
  "schema_version": "1.0",
  "synthetic": false,
  "cases": [
    {
      "id": "pilot-01",
      "before": "pilot-01/before.png",
      "after": "pilot-01/after.png",
      "truth": "pilot-01/reference.png",
      "valid_mask": "pilot-01/usable.png",
      "evaluation_mask": "pilot-01/annotated.png",
      "metadata": {
        "site": "Pilot 01",
        "before_date": "2025-06-01",
        "after_date": "2026-06-01",
        "source": "Record the actual image provider and license here"
      }
    }
  ]
}
```

| Field | Rule |
| --- | --- |
| `schema_version` | Required string `"1.0"` |
| `synthetic` | Boolean; defaults to false; use true for generated data |
| `cases` | Nonempty list; case IDs must be unique |
| `id` | 1–64 letters, digits, underscores or hyphens; first character must be alphanumeric |
| `before`, `after`, `truth` | Required image paths; images follow the same input rules as the single-pair CLI |
| `valid_mask` | Optional: usable on both dates; controls detection and evaluation |
| `evaluation_mask` | Optional: labelled pixels; controls evaluation coverage without restricting detection |
| `metadata` | Optional provenance object using the [single-pair fields](EXPERIMENTS.md) |

Paths are relative to the manifest directory, independently of the terminal's current directory. Absolute paths also work. Unknown fields, invalid dates and empty annotation/usable intersections are errors. Black reference pixels mean known unchanged inside annotation coverage. Without an evaluation mask, all usable pixels are assumed labelled.

Run your own manifest with fixed settings:

```bash
python -m change_watch.benchmark data/held-out.json --threshold 35 --min-pixels 25 --connectivity 4 --corrections none median_offset --out outputs/held-out
```

Use `--corrections none` for baseline-only evaluation. Choose settings on separate tuning examples, then keep them fixed for held-out pairs. The runner does not verify that cases are independent or that annotations are correct. Keep generated and real data in separate manifests so provenance labels remain accurate.

## Read the outputs

- `benchmark.json` contains the settings, benchmark ID, canonical manifest hash, summaries and full per-case analysis reports, including pixel fingerprints and annotation coverage.
- `cases.csv` has one row per case and correction: run ID, coverage, detections, confusion counts and precision/recall/F1/IoU. Undefined metrics are empty CSV cells and JSON `null`.

Pooled (`micro`) metrics sum confusion counts across pairs before computing ratios; pairs with more evaluated pixels have more influence. Macro metrics average each defined per-pair metric equally. `macro_defined_cases` states how many pairs contributed to each average. A stable pair with no predicted or reference positives has undefined IoU, so it contributes its true-negative count to pooled counts and is omitted from the macro IoU mean. An all-undefined macro mean stays `null`.

The benchmark ID hashes ordered case IDs, correction names and per-case run IDs. It stays stable across timestamps and directory changes when inputs/settings/provenance are unchanged. The manifest hash covers canonical JSON, including paths. Batch outputs summarize experiments; they do not copy source imagery. Retain your input dataset and manifest, or use the single-pair CLI to export portable image bundles for selected cases.
