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
    evaluation_mask: np.ndarray | None = None


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
    evaluation_mask=None,
    connectivity=4,
    correction="none",
    synthetic=False,
    metadata=None,
    sensitivity=False,
    acquisition=None,
):
    metadata = validate_metadata(metadata)
    if acquisition is not None:
        # Retain an independent JSON value in the identity and report. The
        # satellite workflow supplies it; offline replay can load its export.
        try:
            acquisition = json.loads(json.dumps(acquisition, allow_nan=False))
            grid = acquisition["grid"]
            image_shape = np.shape(before)
            if (
                synthetic
                or len(image_shape) != 3
                or acquisition["schema_version"] != "1.0"
                or acquisition["collection"] != "sentinel-2-c1-l2a"
                or not isinstance(acquisition["aoi"], dict)
                or acquisition["aoi"].get("type") != "Polygon"
                or not isinstance(acquisition["aoi"].get("coordinates"), list)
                or grid["width"] != image_shape[1]
                or grid["height"] != image_shape[0]
                or not isinstance(grid["crs"], str)
                or len(grid["transform"]) != 6
                or not all(np.isfinite(value) for value in grid["transform"])
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, IndexError) as error:
            raise ValueError(
                "Satellite provenance must describe the matching comparison grid."
            ) from error
    if evaluation_mask is not None and truth is None:
        raise ValueError("An evaluation mask requires a reference change mask.")
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
    evaluation_valid = None
    if truth is not None:
        evaluation_valid = result.valid
        if evaluation_mask is not None:
            annotated = np.asarray(evaluation_mask)
            if annotated.shape != result.valid.shape or annotated.dtype != np.bool_:
                raise ValueError("Evaluation mask must be boolean and match the image dimensions.")
            evaluation_valid = result.valid & annotated
        # Validate before fingerprinting/exporting a user-supplied reference.
        evaluation = evaluate_mask(result.mask, truth, evaluation_valid)
        inputs["reference_mask"] = array_fingerprint(truth)
        inputs["evaluation_mask"] = array_fingerprint(evaluation_valid)
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
    if acquisition is not None:
        identity["acquisition"] = acquisition
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
        "schema_version": "1.1",
        "software_version": __version__,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": (
            "sentinel_2_collection_1"
            if acquisition is not None
            else "synthetic_demo"
            if synthetic
            else "user_supplied_rgb_images"
        ),
        "metadata": metadata,
        "input_pixel_sha256": inputs,
        "coordinates": "zero-based pixel coordinates; x_max/y_max exclusive; no georeferencing",
        "regions": result.regions,
        "warnings": warnings,
    }
    if acquisition is not None:
        report["schema_version"] = "1.2"
        report["acquisition"] = acquisition
        report["coordinates"] = (
            "Region boxes are zero-based, half-open pixel coordinates; "
            "acquisition.grid maps pixel edges to the recorded projected CRS."
        )
        warnings[0] = (
            "Both dates were resampled to one geographic grid; residual sensor misregistration is possible."
        )
        warnings.append(
            "SCL cloud screening is imperfect and has 20 m native resolution; inspect the imagery."
        )
    if truth is not None:
        report["evaluation"] = evaluation
        report["evaluation_pixels"] = int(evaluation_valid.sum())
        report["evaluation_fraction_of_usable"] = (
            report["evaluation_pixels"] / report["valid_pixels"]
        )
        report["unevaluated_usable_pixels"] = report["valid_pixels"] - report["evaluation_pixels"]
        report["evaluation_scope"] = (
            "Synthetic pipeline check only; not evidence of real-world accuracy."
            if synthetic
            else "User-provided reference on annotated, usable pixels; annotation quality is not verified."
        )
        if report["unevaluated_usable_pixels"]:
            warnings.append(
                "Reference metrics cover only annotated usable pixels; detection still covers all usable pixels."
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
    return Analysis(result, report, evaluation_valid)
