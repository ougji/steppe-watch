import unittest

import numpy as np

from change_watch.core import detect_changes, evaluate_mask, make_overlay
from change_watch.demo import synthetic_pair


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.before = np.zeros((10, 10, 3), dtype=np.uint8)

    def test_identical_images_have_no_change(self):
        result = detect_changes(self.before, self.before, threshold=0, min_pixels=1)
        self.assertFalse(result.mask.any())
        self.assertEqual(result.summary["candidate_regions"], 0)

    def test_darkening_does_not_wrap_unsigned_integers(self):
        bright = np.full_like(self.before, 255)
        result = detect_changes(bright, self.before, threshold=254, min_pixels=1)
        self.assertEqual(result.summary["changed_pixels"], 100)
        self.assertTrue((result.score == 255).all())

    def test_small_regions_are_filtered(self):
        after = self.before.copy()
        after[1:3, 1:3] = 255
        after[8, 8] = 255
        result = detect_changes(self.before, after, threshold=35, min_pixels=4)
        self.assertEqual(result.summary["changed_pixels"], 4)
        self.assertEqual(result.summary["candidate_regions"], 1)

    def test_diagonal_pixels_are_separate_regions(self):
        after = self.before.copy()
        after[1, 1] = after[2, 2] = 255
        result = detect_changes(self.before, after, min_pixels=2)
        self.assertFalse(result.mask.any())

    def test_excluded_pixels_do_not_affect_percent_or_regions(self):
        after = np.full_like(self.before, 255)
        valid = np.zeros((10, 10), dtype=bool)
        valid[:2, :2] = True
        result = detect_changes(self.before, after, min_pixels=1, valid_mask=valid)
        self.assertEqual(result.summary["valid_pixels"], 4)
        self.assertEqual(result.summary["changed_fraction"], 1)
        self.assertEqual(int(result.mask.sum()), 4)
        self.assertTrue((result.score[~valid] == 0).all())

    def test_mismatched_dimensions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "same dimensions"):
            detect_changes(self.before, np.zeros((9, 10, 3), dtype=np.uint8))

    def test_all_excluded_pixels_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "excludes every"):
            detect_changes(self.before, self.before, valid_mask=np.zeros((10, 10), dtype=bool))

    def test_bad_controls_are_rejected(self):
        for value in [-1, 256, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                detect_changes(self.before, self.before, threshold=value)
        for value in [0, -1, 1.5, True]:
            with self.assertRaises(ValueError):
                detect_changes(self.before, self.before, min_pixels=value)

    def test_non_rgb_and_non_uint8_images_are_rejected(self):
        for image in [self.before[:, :, 0], self.before.astype(float), np.zeros((0, 0, 3), dtype=np.uint8)]:
            with self.assertRaises(ValueError):
                detect_changes(image, image)

    def test_synthetic_ground_truth_is_recovered(self):
        before, after, truth = synthetic_pair()
        result = detect_changes(before, after)
        self.assertTrue(np.array_equal(result.mask, truth))
        self.assertEqual(evaluate_mask(result.mask, truth)["iou"], 1)

    def test_evaluation_counts_false_positives_and_negatives(self):
        predicted = np.array([[True, True], [False, False]])
        truth = np.array([[True, False], [True, False]])
        metrics = evaluate_mask(predicted, truth)
        self.assertEqual(metrics["true_positive_pixels"], 1)
        self.assertEqual(metrics["false_positive_pixels"], 1)
        self.assertEqual(metrics["false_negative_pixels"], 1)
        self.assertAlmostEqual(metrics["f1"], 0.5)
        self.assertAlmostEqual(metrics["iou"], 1 / 3)

    def test_empty_positive_class_has_undefined_metrics(self):
        mask = np.zeros((2, 2), dtype=bool)
        metrics = evaluate_mask(mask, mask)
        self.assertIsNone(metrics["precision"])
        self.assertIsNone(metrics["recall"])
        self.assertIsNone(metrics["f1"])
        self.assertIsNone(metrics["iou"])

    def test_overlay_preserves_unflagged_pixels_and_inputs(self):
        image = np.full_like(self.before, 80)
        mask = np.zeros((10, 10), dtype=bool)
        mask[0, 0] = True
        overlay = make_overlay(image, mask)
        self.assertTrue(np.array_equal(overlay[~mask], image[~mask]))
        self.assertFalse(np.array_equal(overlay[0, 0], image[0, 0]))
        self.assertTrue((image == 80).all())


if __name__ == "__main__":
    unittest.main()
