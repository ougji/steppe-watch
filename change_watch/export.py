"""Portable, reproducible experiment artifacts shared by app and CLI."""

import csv
import io
import json
import zipfile

import numpy as np

from .core import make_overlay
from .io import png_bytes

REGION_FIELDS = ["region_id", "pixels", "mean_difference", "x_min", "y_min", "x_max", "y_max"]


def regions_csv(regions):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REGION_FIELDS)
    writer.writeheader()
    writer.writerows(regions)
    return output.getvalue().encode("utf-8")


def build_artifacts(analysis, before, after, truth=None):
    """Include decoded inputs so the analysis can be rerun without original files."""
    result, report = analysis.result, analysis.report
    command = (
        "python -m change_watch --before before.png --after after.png "
        "--valid-mask usable_mask.png --metadata metadata.json "
        f"--threshold {report['threshold']:g} --min-pixels {report['minimum_region_pixels']} "
        f"--connectivity {report['connectivity']} --correction {report['correction']}"
    )
    if truth is not None:
        command += " --truth reference_mask.png"
    if "sensitivity" in report:
        command += " --sensitivity"
    command += " --out reproduced"
    # NPY preserves fractional scores; difference.png is only an 8-bit preview.
    score_file = io.BytesIO()
    np.save(score_file, result.score, allow_pickle=False)
    artifacts = {
        "before.png": png_bytes(before),
        "after.png": png_bytes(after),
        "usable_mask.png": png_bytes(result.valid),
        "change_mask.png": png_bytes(result.mask),
        "overlay.png": png_bytes(make_overlay(after, result.mask)),
        "difference.png": png_bytes(result.score.astype(np.uint8)),
        "scores.npy": score_file.getvalue(),
        "report.json": (json.dumps(report, indent=2, allow_nan=False) + "\n").encode("utf-8"),
        "regions.csv": regions_csv(result.regions),
        "metadata.json": (json.dumps(report["metadata"], indent=2) + "\n").encode("utf-8"),
        "REPRODUCE.txt": (
            f"Steppe Watch {report['software_version']} | Run {report['run_id']}\n"
            f"Source: {report['data_source']}\n\n"
            "Install the matching Steppe Watch version, then run inside this directory:\n\n"
            f"{command}\n\n"
            "The PNG inputs are decoded, EXIF-oriented crops, not original provider products.\n"
            "The report hashes decoded arrays (dtype, shape, then contiguous pixel bytes).\n"
            "Re-running exported synthetic inputs uses user-supplied source labels. Pixel outputs\n"
            "and evaluation remain reproducible; run IDs and timestamps may differ.\n"
            "Black pixels in difference.png may be excluded OR unchanged; consult usable_mask.png.\n"
            "Region boxes are half-open pixel coordinates, not geographic coordinates.\n"
        ).encode("utf-8"),
    }
    if truth is not None:
        artifacts["reference_mask.png"] = png_bytes(truth)
    return artifacts


def zip_artifacts(artifacts):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in artifacts.items():
            archive.writestr(name, content)
    return output.getvalue()
