import contextlib
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from change_watch.benchmark import benchmark_artifacts, main, read_manifest, run_benchmark
from change_watch.io import png_bytes

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cases = []

    def case(self, identifier, size, changed, truth):
        before = np.zeros((size, size, 3), dtype=np.uint8)
        after = before.copy()
        reference = np.zeros((size, size), dtype=bool)
        for y, x in changed:
            after[y, x] = 255
        for y, x in truth:
            reference[y, x] = True
        case = {"id": identifier}
        for key, array in (("before", before), ("after", after), ("truth", reference)):
            case[key] = f"{identifier}-{key}.png"
            (self.root / case[key]).write_bytes(png_bytes(array))
        self.cases.append(case)
        return case

    def manifest(self, **options):
        path = self.root / "cases.json"
        path.write_text(
            json.dumps(
                {"schema_version": "1.0", "synthetic": True, "cases": self.cases, **options}
            ),
            encoding="utf-8",
        )
        return path

    def test_micro_and_macro_metrics_have_different_weights(self):
        self.case("small", 2, [(0, 0)], [(0, 0)])
        self.case("larger", 3, [(0, 0), (0, 1), (0, 2)], [(0, 0)])
        result = run_benchmark(self.manifest(), min_pixels=1, corrections=["none"])
        summary = result["summaries"][0]
        self.assertEqual(summary["evaluation_pixels"], 13)
        self.assertEqual(summary["micro"]["true_positive_pixels"], 2)
        self.assertEqual(summary["micro"]["false_positive_pixels"], 2)
        self.assertEqual(summary["micro"]["iou"], 0.5)
        self.assertAlmostEqual(summary["macro"]["iou"], 2 / 3)
        self.assertEqual(summary["macro_defined_cases"]["iou"], 2)
        files = benchmark_artifacts(result)
        rows = list(csv.DictReader(io.StringIO(files["cases.csv"].decode())))
        self.assertEqual([row["case_id"] for row in rows], ["small", "larger"])
        self.assertEqual(
            json.loads(files["benchmark.json"])["benchmark_id"], result["benchmark_id"]
        )

    def test_undefined_metrics_remain_null_with_defined_case_counts(self):
        self.case("stable", 2, [], [])
        path = self.manifest()
        result = run_benchmark(path, min_pixels=1)
        for summary in result["summaries"]:
            self.assertIsNone(summary["micro"]["iou"])
            self.assertIsNone(summary["macro"]["iou"])
            self.assertEqual(summary["macro_defined_cases"]["iou"], 0)
        self.case("changed", 2, [(0, 0)], [(0, 0)])
        result = run_benchmark(self.manifest(), min_pixels=1, corrections=["none"])
        summary = result["summaries"][0]
        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["macro_defined_cases"]["iou"], 1)
        self.assertEqual(summary["macro"]["iou"], 1)

    def test_partial_coverage_and_usable_masks_are_shared_by_variants(self):
        case = self.case("partial", 3, [(0, 0), (0, 1), (0, 2)], [(0, 0)])
        annotated = np.zeros((3, 3), dtype=bool)
        annotated[0, 0] = True
        valid = np.ones_like(annotated)
        valid[0, 2] = False
        for key, mask in (("evaluation_mask", annotated), ("valid_mask", valid)):
            case[key] = f"{key}.png"
            (self.root / case[key]).write_bytes(png_bytes(mask))
        result = run_benchmark(self.manifest(), min_pixels=1)
        self.assertEqual(len(result["results"]), 2)
        for row in result["results"]:
            report = row["report"]
            self.assertEqual(report["valid_pixels"], 8)
            self.assertEqual(report["changed_pixels"], 2)
            self.assertEqual(report["evaluation_pixels"], 1)
            self.assertEqual(report["evaluation"]["iou"], 1)

    def test_benchmark_keeps_a_regression_when_correction_hides_widespread_change(self):
        changed = [(y, x) for y in range(3) for x in range(3)]
        self.case("widespread", 3, changed, changed)
        result = run_benchmark(self.manifest(), min_pixels=1)
        variants = {row["correction"]: row for row in result["summaries"]}
        self.assertEqual(variants["none"]["micro"]["iou"], 1)
        self.assertEqual(variants["median_offset"]["micro"]["iou"], 0)
        self.assertEqual(variants["median_offset"]["micro"]["false_negative_pixels"], 9)

    def test_identity_is_stable_but_changes_with_pixels_settings_and_case_ids(self):
        case = self.case("first", 3, [(0, 0)], [(0, 0)])
        path = self.manifest()
        result = run_benchmark(path)
        self.assertEqual(result["benchmark_id"], run_benchmark(path)["benchmark_id"])
        self.assertNotEqual(
            result["benchmark_id"], run_benchmark(path, threshold=40)["benchmark_id"]
        )
        case["id"] = "renamed"
        self.assertNotEqual(result["benchmark_id"], run_benchmark(self.manifest())["benchmark_id"])
        case["id"] = "first"
        (self.root / case["after"]).write_bytes(png_bytes(np.zeros((3, 3, 3), dtype=np.uint8)))
        self.assertNotEqual(result["benchmark_id"], run_benchmark(self.manifest())["benchmark_id"])

    def test_invalid_manifests_fail_before_analysis(self):
        good = self.case("good", 2, [], [])
        manifests = [
            [],
            {},
            {"schema_version": "2.0", "cases": [good]},
            {"schema_version": "1.0", "cases": []},
            {"schema_version": "1.0", "synthetic": "yes", "cases": [good]},
            {"schema_version": "1.0", "cases": [good], "typo": True},
        ]
        for case in (
            [],
            {},
            {**good, "id": "../bad"},
            {**good, "truth": ""},
            {**good, "after": None},
            {**good, "unknown": "x"},
            {**good, "metadata": {"site": 42}},
        ):
            manifests.append({"schema_version": "1.0", "cases": [case]})
        manifests.append({"schema_version": "1.0", "cases": [good, good]})
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                path = self.root / "invalid.json"
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    read_manifest(path)

    def test_invalid_settings_and_missing_images_fail_without_output(self):
        self.case("broken", 2, [], [])
        manifest = self.manifest()
        for corrections in ([], "none", ["invalid"], ["none", "none"]):
            with self.subTest(corrections=corrections), self.assertRaises(ValueError):
                run_benchmark(manifest, corrections=corrections)
        self.cases[0]["truth"] = "missing.png"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            main([str(self.manifest()), "--out", str(self.root / "output")])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("Case 'broken'", stderr.getvalue())
        self.assertFalse((self.root / "output").exists())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_resolves_manifest_paths_from_another_working_directory(self):
        target = self.root / "output"
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "change_watch.benchmark",
                str(ROOT / "examples/benchmark.json"),
                "--out",
                str(target),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads((target / "benchmark.json").read_text())
        self.assertEqual(report["case_count"], 2)
        self.assertEqual(report["data_source"], "synthetic_demo")
        variants = {row["correction"]: row for row in report["summaries"]}
        self.assertEqual(variants["median_offset"]["micro"]["iou"], 1)
        self.assertLess(variants["none"]["micro"]["iou"], 1)
        marker = (target / "benchmark.json").read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([str(ROOT / "examples/benchmark.json"), "--out", str(target)])
        self.assertEqual((target / "benchmark.json").read_bytes(), marker)
