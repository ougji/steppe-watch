"""Deterministic RGB change detection; no geographic or ML claims."""

from dataclasses import dataclass, field
from numbers import Real

import numpy as np
from scipy.ndimage import find_objects, generate_binary_structure, label


@dataclass
class ChangeResult:
    score: np.ndarray
    mask: np.ndarray
    valid: np.ndarray
    summary: dict
    regions: list[dict] = field(default_factory=list)
    labels: np.ndarray | None = None


def detect_changes(
    before,
    after,
    threshold=35.0,
    min_pixels=25,
    valid_mask=None,
    *,
    connectivity=4,
    correction="none",
):
    """Compare aligned uint8 RGB arrays, preserving the v0.1 default method.

    ``median_offset`` subtracts a per-channel median signed difference over
    usable pixels. It assumes most usable land is stable and can suppress real
    widespread changes; it is opt-in and the estimated offset is reported.
    Region boxes use zero-based, half-open pixel coordinates (never lon/lat).
    """
    before, after = np.asarray(before), np.asarray(after)
    if before.shape != after.shape:
        raise ValueError("Images must have the same dimensions and cover the same aligned area.")
    if before.ndim != 3 or before.shape[2] != 3 or not before.size:
        raise ValueError("Images must be nonempty H x W x 3 RGB arrays.")
    if before.dtype != np.uint8 or after.dtype != np.uint8:
        raise ValueError("This baseline accepts uint8 RGB images with values from 0 to 255.")
    if (
        isinstance(threshold, (bool, np.bool_))
        or not isinstance(threshold, Real)
        or not np.isfinite(threshold)
        or not 0 <= threshold <= 255
    ):
        raise ValueError("Threshold must be a finite number from 0 to 255.")
    if (
        isinstance(min_pixels, bool)
        or not isinstance(min_pixels, (int, np.integer))
        or min_pixels < 1
    ):
        raise ValueError("Minimum region size must be a positive integer.")
    if isinstance(connectivity, (bool, np.bool_)) or connectivity not in (4, 8):
        raise ValueError("Connectivity must be 4 or 8.")
    if correction not in ("none", "median_offset"):
        raise ValueError("Correction must be 'none' or 'median_offset'.")
    if valid_mask is None:
        valid = np.ones(before.shape[:2], dtype=bool)
    else:
        valid = np.asarray(valid_mask)
        if valid.shape != before.shape[:2] or valid.dtype != np.bool_:
            raise ValueError(
                "Valid mask must be a boolean array matching the image height and width."
            )
    valid_count = int(valid.sum())
    if not valid_count:
        raise ValueError("The valid mask excludes every pixel; there is nothing to compare.")

    delta = after.astype(np.float32) - before.astype(np.float32)
    raw_mean = float(np.abs(delta[valid]).mean(dtype=np.float64))
    offset = (
        np.median(delta[valid], axis=0).astype(np.float64)
        if correction == "median_offset"
        else np.zeros(3)
    )
    # Bound residuals to the same 0–255 score scale as the original baseline.
    score = np.minimum(np.abs(delta - offset).mean(axis=2), 255.0)
    score = np.where(valid, score, 0.0)
    candidate = (score > threshold) & valid
    labels, _ = label(
        candidate, structure=generate_binary_structure(2, 1 if connectivity == 4 else 2)
    )
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_pixels
    keep[0] = False
    mask = keep[labels]
    # Dense row-major IDs allow direct lookup without full-image scans per region.
    remap = np.zeros(len(keep), dtype=np.int32)
    remap[keep] = np.arange(1, int(keep.sum()) + 1)
    labels = remap[labels]
    regions = region_statistics(labels, score)
    changed_count = int(mask.sum())
    return ChangeResult(
        score,
        mask,
        valid,
        {
            "method": "mean_absolute_rgb_difference",
            "threshold": float(threshold),
            "minimum_region_pixels": int(min_pixels),
            "connectivity": int(connectivity),
            "correction": correction,
            "channel_offset_rgb": offset.tolist(),
            "raw_mean_difference": raw_mean,
            "width": int(before.shape[1]),
            "height": int(before.shape[0]),
            "valid_pixels": valid_count,
            "excluded_pixels": int(valid.size - valid_count),
            "usable_fraction": valid_count / valid.size,
            "raw_candidate_pixels": int(candidate.sum()),
            "filtered_pixels": int(candidate.sum()) - changed_count,
            "changed_pixels": changed_count,
            "changed_fraction": changed_count / valid_count,
            "candidate_regions": len(regions),
            "mean_difference": float(score[valid].mean()),
            "interpretation": "Candidate visual changes for human review; not mining or legal determinations.",
        },
        regions,
        labels,
    )


def region_statistics(labels, score):
    """Return retained component statistics ordered by size, then region ID."""
    count = int(labels.max())
    if not count:
        return []
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    sums = np.bincount(labels.ravel(), weights=score.ravel(), minlength=count + 1)
    regions = []
    for region_id, box in enumerate(find_objects(labels), start=1):
        rows, cols = box
        regions.append(
            {
                "region_id": region_id,
                "pixels": int(sizes[region_id]),
                "mean_difference": float(sums[region_id] / sizes[region_id]),
                "x_min": cols.start,
                "y_min": rows.start,
                "x_max": cols.stop,
                "y_max": rows.stop,
            }
        )
    return sorted(regions, key=lambda r: (-r["pixels"], r["region_id"]))


def threshold_sweep(score, valid, thresholds, min_pixels=25, connectivity=4):
    """Measure parameter sensitivity without selecting a winner."""
    if (
        isinstance(min_pixels, bool)
        or not isinstance(min_pixels, (int, np.integer))
        or min_pixels < 1
    ):
        raise ValueError("Minimum region size must be a positive integer.")
    if isinstance(connectivity, (bool, np.bool_)) or connectivity not in (4, 8):
        raise ValueError("Connectivity must be 4 or 8.")
    score, valid = np.asarray(score), np.asarray(valid)
    if (
        score.ndim != 2
        or valid.shape != score.shape
        or valid.dtype != np.bool_
        or not valid.any()
        or not np.isfinite(score).all()
        or (score < 0).any()
        or (score > 255).any()
    ):
        raise ValueError("Sensitivity needs finite 0–255 scores and a matching usable mask.")
    rows = []
    for threshold in sorted(set(thresholds)):
        if (
            isinstance(threshold, (bool, np.bool_))
            or not isinstance(threshold, Real)
            or not np.isfinite(threshold)
            or not 0 <= threshold <= 255
        ):
            raise ValueError("Threshold must be a finite number from 0 to 255.")
        components, _ = label(
            (score > threshold) & valid,
            structure=generate_binary_structure(2, 1 if connectivity == 4 else 2),
        )
        sizes = np.bincount(components.ravel())[1:]
        retained = sizes[sizes >= min_pixels]
        rows.append(
            {
                "threshold": float(threshold),
                "changed_pixels": int(retained.sum()),
                "changed_fraction": float(retained.sum() / valid.sum()),
                "candidate_regions": len(retained),
            }
        )
    return rows


def make_overlay(after, mask):
    after, mask = np.asarray(after), np.asarray(mask)
    if after.ndim != 3 or after.shape[2] != 3 or after.dtype != np.uint8:
        raise ValueError("Overlay image must be uint8 RGB.")
    if mask.shape != after.shape[:2] or mask.dtype != np.bool_:
        raise ValueError("Overlay mask must be boolean and match the image dimensions.")
    result = after.copy()
    result[mask] = (0.4 * after[mask] + 0.6 * np.array([255, 73, 35])).astype(np.uint8)
    return result


def evaluate_mask(predicted, truth, valid_mask=None):
    predicted, truth = np.asarray(predicted), np.asarray(truth)
    if predicted.ndim != 2 or predicted.shape != truth.shape:
        raise ValueError("Predicted and reference masks must be matching 2D arrays.")
    if predicted.dtype != np.bool_ or truth.dtype != np.bool_:
        raise ValueError("Evaluation masks must be boolean.")
    valid = np.ones(truth.shape, dtype=bool) if valid_mask is None else np.asarray(valid_mask)
    if valid.shape != truth.shape or valid.dtype != np.bool_ or not valid.any():
        raise ValueError("Evaluation needs a matching boolean mask with some valid pixels.")
    tp = int((predicted & truth & valid).sum())
    fp = int((predicted & ~truth & valid).sum())
    fn = int((~predicted & truth & valid).sum())
    tn = int((~predicted & ~truth & valid).sum())

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    return {
        "true_positive_pixels": tp,
        "false_positive_pixels": fp,
        "false_negative_pixels": fn,
        "true_negative_pixels": tn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "iou": ratio(tp, tp + fp + fn),
    }
