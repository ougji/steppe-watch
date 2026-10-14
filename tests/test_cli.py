import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from change_watch.__main__ import main
from change_watch.io import png_bytes


class CommandLineTests(unittest.TestCase):
    def test_module_demo_creates_complete_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "run"
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "change_watch",
                    "--demo",
                    "--sensitivity",
                    "--zip",
                    "--out",
                    str(target),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue((target / "experiment.zip").is_file())
            report = json.loads((target / "report.json").read_text())
            self.assertEqual(report["evaluation"]["iou"], 1)
            self.assertEqual(report["data_source"], "synthetic_demo")
            self.assertIn("sensitivity", report)

    def test_input_images_with_masks_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = np.zeros((3, 4, 3), dtype=np.uint8)
            after = before.copy()
            after[0, 0] = 255
            mask = np.ones((3, 4), dtype=bool)
            mask[0, 0] = False
            for name, array in (
                ("before", before),
                ("after", after),
                ("valid", mask),
                ("truth", ~mask),
            ):
                (root / f"{name}.png").write_bytes(png_bytes(array))
            (root / "metadata.json").write_text('{"site": "Test site"}')
            with contextlib.redirect_stdout(io.StringIO()):
                main(
                    [
                        "--before",
                        str(root / "before.png"),
                        "--after",
                        str(root / "after.png"),
                        "--valid-mask",
                        str(root / "valid.png"),
                        "--truth",
                        str(root / "truth.png"),
                        "--metadata",
                        str(root / "metadata.json"),
                        "--min-pixels",
                        "1",
                        "--out",
                        str(root / "out"),
                    ]
                )
            report = json.loads((root / "out/report.json").read_text())
            self.assertEqual(report["changed_pixels"], 0)
            self.assertEqual(report["metadata"]["site"], "Test site")
            self.assertIsNone(report["evaluation"]["iou"])
            self.assertEqual(report["data_source"], "user_supplied_rgb_images")

    def test_usage_errors_are_clear(self):
        for arguments in (
            [],
            ["--demo", "--before", "x"],
            ["--demo", "--threshold", "nan"],
            ["--before", "missing.png", "--after", "missing.png"],
        ):
            with tempfile.TemporaryDirectory() as directory:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                    main([*arguments, "--out", str(Path(directory) / "out")])
                self.assertEqual(error.exception.code, 2)
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertFalse((Path(directory) / "out").exists())

    def test_existing_experiment_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "report.json"
            marker.write_text("existing report")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--demo", "--out", directory])
            self.assertEqual(marker.read_text(), "existing report")

    def test_malformed_metadata_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.json").write_text("[]")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--demo", "--metadata", str(root / "bad.json"), "--out", str(root / "out")])
            self.assertFalse((root / "out").exists())
