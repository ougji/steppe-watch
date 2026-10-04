from dataclasses import dataclass

import numpy as np
from scipy.ndimage import label


@dataclass
class ChangeResult:
    score: np.ndarray
    mask: np.ndarray
    valid: np.ndarray
    summary: dict


def detect_changes(before, after, threshold=35.0, min_pixels=25, valid_mask=None):
    before, after = np.asarray(before), np.asarray(after)
    if before.shape != after.shape:
        raise ValueError("Images must have the same dimensions and cover the same aligned area.")
    if before.ndim != 3 or before.shape[2] != 3 or not before.size:
        raise ValueError("Images must be nonempty H x W x 3 RGB arrays.")
    if before.dtype != np.uint8 or after.dtype != np.uint8:
        raise ValueError("This baseline accepts uint8 RGB images with values from 0 to 255.")
    if not np.isfinite(threshold) or not 0 <= threshold <= 255:
        raise ValueError("Threshold must be a finite number from 0 to 255.")
    if isinstance(min_pixels, bool) or not isinstance(min_pixels, (int, np.integer)) or min_pixels < 1:
        raise ValueError("Minimum region size must be a positive integer.")
    if valid_mask is None:
        valid = np.ones(before.shape[:2], dtype=bool)
    else:
        valid = np.asarray(valid_mask)
        if valid.shape != before.shape[:2] or valid.dtype != np.bool_:
            raise ValueError("Valid mask must be a boolean array matching the image height and width.")
    valid_count = int(valid.sum())
    if not valid_count:
        raise ValueError("The valid mask excludes every pixel; there is nothing to compare.")

    score = np.abs(after.astype(np.int16) - before.astype(np.int16)).mean(axis=2)
    score = np.where(valid, score, 0.0)
    candidate = (score > threshold) & valid
    labels, _ = label(candidate)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_pixels
    keep[0] = False
    mask = keep[labels]
    regions = int(keep.sum())
    changed_count = int(mask.sum())
    return ChangeResult(score, mask, valid, {
        "method": "mean_absolute_rgb_difference",
        "threshold": float(threshold),
        "minimum_region_pixels": int(min_pixels),
        "connectivity": 4,
        "width": int(before.shape[1]),
        "height": int(before.shape[0]),
        "valid_pixels": valid_count,
        "changed_pixels": changed_count,
        "changed_fraction": changed_count / valid_count,
        "candidate_regions": regions,
        "mean_difference": float(score[valid].mean()),
        "interpretation": "Candidate visual changes for human review; not mining or legal determinations.",
    })


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
