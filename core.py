"""Compatibility exports; implementation lives in change_watch.core."""

from change_watch.core import ChangeResult, detect_changes, evaluate_mask, make_overlay

__all__ = ["ChangeResult", "detect_changes", "evaluate_mask", "make_overlay"]
