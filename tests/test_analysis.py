import io
import json
import unittest
import zipfile

import numpy as np

from change_watch.analysis import analyze_pair, array_fingerprint, validate_metadata
from change_watch.core import detect_changes, evaluate_mask, threshold_sweep
from change_watch.demo import synthetic_pair
from change_watch.export import build_artifacts, zip_artifacts
from change_watch.io import load_image


class AnalysisTests(unittest.TestCase):
    def test_corrected_score_uses_full_precision_at_threshold_boundary(self):
        before = np.zeros((3, 3, 3), dtype=np.uint8)
        after = before.copy()
        after[0, 0, 0] = 100
        result = detect_changes(
            before, after, threshold=33.3333325, min_pixels=1, correction="median_offset"
        )
        self.assertTrue(result.mask[0, 0])

    def test_region_boxes_ids_sizes_and_means(self):
        before = np.zeros((8, 9, 3), dtype=np.uint8)
        after = before.copy()
        after[0:2, 1:3] = 90
        after[4:7, 6:9] = 120
        result = detect_changes(before, after, min_pixels=1)
        large, small = result.regions
        self.assertEqual(
            large,
            {
                "region_id": 2,
                "pixels": 9,
                "mean_difference": 120.0,
                "x_min": 6,
                "y_min": 4,
                "x_max": 9,
                "y_max": 7,
            },
        )
        self.assertEqual(small["pixels"], 4)
        self.assertEqual(result.labels[0, 1], 1)
        np.testing.assert_array_equal(result.labels > 0, result.mask)

    def test_eight_connected_diagonal_region(self):
        before = np.zeros((3, 3, 3), dtype=np.uint8)
        after = before.copy()
        after[0, 0] = after[1, 1] = 255
        self.assertEqual(
            detect_changes(before, after, min_pixels=2, connectivity=8).summary["changed_pixels"], 2
        )

    def test_filtered_components_have_dense_ids(self):
        before = np.zeros((4, 4, 3), dtype=np.uint8)
        after = before.copy()
        after[0, 0] = 255
        after[2, 2:4] = 255
        result = detect_changes(before, after, min_pixels=2)
        self.assertEqual(result.labels[2, 2], 1)
        self.assertEqual(result.summary["filtered_pixels"], 1)

    def test_median_correction_removes_global_offset_but_keeps_local_change(self):
        before = np.full((10, 10, 3), 80, dtype=np.uint8)
        after = np.full_like(before, 125)
        after[2:4, 3:5] = 200
        raw = detect_changes(before, after, min_pixels=1)
        corrected = detect_changes(before, after, min_pixels=1, correction="median_offset")
        self.assertEqual(raw.summary["changed_pixels"], 100)
        self.assertEqual(corrected.summary["changed_pixels"], 4)
        self.assertEqual(corrected.summary["channel_offset_rgb"], [45, 45, 45])
        self.assertTrue((before == 80).all())

    def test_offset_ignores_excluded_pixels(self):
        before = np.full((10, 10, 3), 80, dtype=np.uint8)
        after = np.full_like(before, 200)
        after[:2, :2] = 90
        valid = np.zeros((10, 10), dtype=bool)
        valid[:2, :2] = True
        result = detect_changes(before, after, valid_mask=valid, correction="median_offset")
        self.assertEqual(result.summary["channel_offset_rgb"], [10, 10, 10])
        self.assertFalse(result.mask.any())

    def test_strict_threshold_on_fractional_channel_mean(self):
        before = np.zeros((1, 1, 3), dtype=np.uint8)
        after = np.array([[[100, 0, 0]]], dtype=np.uint8)
        self.assertFalse(detect_changes(before, after, threshold=100 / 3, min_pixels=1).mask.any())
        self.assertTrue(detect_changes(before, after, threshold=33, min_pixels=1).mask.any())

    def test_sweep_agrees_with_independent_runs(self):
        before, after, _ = synthetic_pair(size=64)
        result = detect_changes(before, after)
        rows = threshold_sweep(result.score, result.valid, [255, 35, 0, 35])
        self.assertEqual(len(rows), 3)
        for row in rows:
            other = detect_changes(before, after, threshold=row["threshold"])
            for key in ("changed_pixels", "changed_fraction", "candidate_regions"):
                self.assertEqual(row[key], other.summary[key])

    def test_invalid_settings_raise_value_error(self):
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        for kwargs in (
            {"threshold": "35"},
            {"threshold": True},
            {"threshold": None},
            {"connectivity": True},
            {"connectivity": 6},
            {"correction": "auto"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                detect_changes(image, image, **kwargs)

    def test_reference_evaluation_ignores_exclusions(self):
        truth = np.ones((2, 2), dtype=bool)
        predicted = np.array([[True, False], [False, False]])
        valid = predicted.copy()
        self.assertEqual(evaluate_mask(predicted, truth, valid)["recall"], 1)

    def test_metadata_validation(self):
        self.assertEqual(validate_metadata({"site": "  Pilot  ", "source": ""}), {"site": "Pilot"})
        for metadata in (
            [],
            {"unknown": "x"},
            {"site": 3},
            {"before_date": "2026-02-30"},
            {"before_date": "20261001"},
            {"before_date": "2026-10-12", "after_date": "2026-10-01"},
        ):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                validate_metadata(metadata)

    def test_run_identity_is_stable_and_sensitive_to_inputs_and_settings(self):
        before, after, truth = synthetic_pair(size=64)
        first = analyze_pair(before, after, truth=truth)
        self.assertEqual(
            first.report["run_id"], analyze_pair(before, after, truth=truth).report["run_id"]
        )
        self.assertNotEqual(
            first.report["run_id"], analyze_pair(before, after, threshold=40).report["run_id"]
        )
        self.assertNotEqual(array_fingerprint(before), array_fingerprint(after))
        self.assertNotEqual(
            array_fingerprint(np.zeros((2, 3), dtype=bool)),
            array_fingerprint(np.zeros((3, 2), dtype=bool)),
        )

    def test_export_round_trip_reproduces_pixels_regions_and_scores(self):
        before, after, truth = synthetic_pair(size=64)
        analysis = analyze_pair(before, after, truth=truth, synthetic=True, sensitivity=True)
        artifacts = build_artifacts(analysis, before, after, truth)
        with zipfile.ZipFile(io.BytesIO(zip_artifacts(artifacts))) as archive:
            self.assertEqual(set(archive.namelist()), set(artifacts))
            report = json.loads(archive.read("report.json"))
            self.assertEqual(report["data_source"], "synthetic_demo")
            replay = analyze_pair(
                load_image(archive.read("before.png")),
                load_image(archive.read("after.png")),
                valid_mask=load_image(archive.read("usable_mask.png"), mask=True),
                truth=load_image(archive.read("reference_mask.png"), mask=True),
            )
            self.assertEqual(report["regions"], replay.report["regions"])
            self.assertEqual(report["evaluation"], replay.report["evaluation"])
            self.assertEqual(report["input_pixel_sha256"], replay.report["input_pixel_sha256"])
            np.testing.assert_array_equal(
                analysis.result.score,
                np.load(io.BytesIO(archive.read("scores.npy")), allow_pickle=False),
            )
            np.testing.assert_array_equal(analysis.result.mask, replay.result.mask)

    def test_empty_export_has_headers_and_json_null(self):
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        truth = np.zeros((2, 2), dtype=bool)
        analysis = analyze_pair(image, image, truth=truth)
        files = build_artifacts(analysis, image, image, truth)
        self.assertEqual(len(files["regions.csv"].splitlines()), 1)
        self.assertIsNone(json.loads(files["report.json"])["evaluation"]["iou"])
