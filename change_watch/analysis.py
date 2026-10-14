"""Shared analysis, provenance and evaluation for every entry point."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np

from . import __version__
from .core import ChangeResult, detect_changes, evaluate_mask, threshold_sweep


@dataclass
class Analysis:
    result: ChangeResult
    report: dict


def array_fingerprint(array):
    """Hash decoded pixels plus their shape/type, independent of PNG metadata."""
    array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(f"{array.dtype}:{array.shape}:".encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def validate_metadata(metadata):
    allowed = {"site", "before_date", "after_date", "source", "notes"}
    if metadata is None:
        return {}
    if not isinstance(metadata, dict) or set(metadata) - allowed:
        raise ValueError(
            "Metadata must be an object with site, before_date, after_date, source or notes."
        )
    if any(not isinstance(value, str) or len(value) > 4000 for value in metadata.values()):
        raise ValueError("Metadata fields must be strings of at most 4000 characters.")
    cleaned = {key: value.strip() for key, value in metadata.items() if value.strip()}
    for key in ("before_date", "after_date"):
        if key in cleaned:
            try:
                parsed = date.fromisoformat(cleaned[key])
                if parsed.isoformat() != cleaned[key]:
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"{key} must be a date in YYYY-MM-DD format.") from error
    if cleaned.get("before_date", "") > cleaned.get("after_date", "9999-12-31"):
        raise ValueError("Before date cannot be later than after date.")
    return cleaned


def analyze_pair(
    before,
    after,
    *,
    threshold=35.0,
    min_pixels=25,
    valid_mask=None,
    truth=None,
    connectivity=4,
    correction="none",
    synthetic=False,
    metadata=None,
    sensitivity=False,
):
    metadata = validate_metadata(metadata)
    result = detect_changes(
        before,
        after,
        threshold,
        min_pixels,
        valid_mask,
        connectivity=connectivity,
        correction=correction,
    )
    inputs = {
        "before": array_fingerprint(before),
        "after": array_fingerprint(after),
        "usable_mask": array_fingerprint(result.valid),
    }
    if truth is not None:
        # Validate before fingerprinting/exporting a user-supplied reference.
        evaluation = evaluate_mask(result.mask, truth, result.valid)
        inputs["reference_mask"] = array_fingerprint(truth)
    settings = {
        key: result.summary[key]
        for key in ("threshold", "minimum_region_pixels", "connectivity", "correction")
    }
    identity = {
        "inputs": inputs,
        "settings": settings,
        "metadata": metadata,
        "version": __version__,
        "synthetic": synthetic,
        "sensitivity": sensitivity,
    }
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    warnings = [
        "Matching dimensions do not verify geographic alignment.",
        "Clouds, shadows, seasons and exposure can cause false alerts.",
        "Pixel counts are not hectares, mining probabilities or legal findings.",
    ]
    if correction != "none":
        warnings.append(
            "Median offset assumes most usable pixels are stable; widespread real change can be suppressed."
        )
    if result.summary["usable_fraction"] < 0.5:
        warnings.append(
            "Less than half the image is usable; the percentage describes only that subset."
        )
    report = {
        **result.summary,
        "schema_version": "1.0",
        "software_version": __version__,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "synthetic_demo" if synthetic else "user_supplied_rgb_images",
        "metadata": metadata,
        "input_pixel_sha256": inputs,
        "coordinates": "zero-based pixel coordinates; x_max/y_max exclusive; no georeferencing",
        "regions": result.regions,
        "warnings": warnings,
    }
    if truth is not None:
        report["evaluation"] = evaluation
        report["evaluation_scope"] = (
            "Synthetic pipeline check only; not evidence of real-world accuracy."
            if synthetic
            else "User-provided reference mask on usable pixels; annotation quality is not verified."
        )
    if sensitivity:
        thresholds = sorted(
            {
                0,
                255,
                float(threshold),
                *(float(np.clip(threshold + step, 0, 255)) for step in (-20, -10, 10, 20)),
            }
        )
        report["sensitivity"] = threshold_sweep(
            result.score, result.valid, thresholds, min_pixels, connectivity
        )
    return Analysis(result, report)
