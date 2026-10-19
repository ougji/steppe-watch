import unittest
from pathlib import Path

import numpy as np
from streamlit.testing.v1 import AppTest

from app import run_analysis

APP = Path(__file__).resolve().parents[1] / "app.py"


class InterfaceTests(unittest.TestCase):
    def test_large_image_cache_sees_a_single_local_change(self):
        before = np.zeros((750, 750, 3), dtype=np.uint8)
        after = before.copy()
        first = run_analysis(before, after, min_pixels=1)
        after[317, 413] = 255
        second = run_analysis(before, after, min_pixels=1)
        self.assertEqual(first.report["changed_pixels"], 0)
        self.assertEqual(second.report["changed_pixels"], 1)
        self.assertNotEqual(first.report["run_id"], second.report["run_id"])

    def app(self):
        return AppTest.from_file(str(APP), default_timeout=30).run()

    def test_demo_and_empty_result_render(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[2].value, "1")
        self.assertEqual(app.metric[7].value, "1.000")
        self.assertTrue(any("100.0% of usable coverage" in item.value for item in app.caption))
        app.slider(key="threshold").set_value(255).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[1].value, "0")
        self.assertTrue(any("No regions pass" in item.value for item in app.info))

    def test_brightness_scenario_correction_and_sensitivity(self):
        app = self.app()
        app.selectbox(key="scenario").select("Expansion + brightness shift").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "100.0%")
        app.checkbox(key="correction").check()
        app.checkbox(key="sensitivity").check().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[7].value, "1.000")
        self.assertTrue(any("changed_fraction" in table.value for table in app.dataframe))

    def test_prepared_bundle_is_invalidated_when_settings_change(self):
        app = self.app()
        app.button(key="prepare").click().run()
        self.assertFalse(app.exception)
        old_id = app.session_state["bundle"][0]
        self.assertGreater(len(app.session_state["bundle"][1]), 0)
        app.slider(key="threshold").set_value(50).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Settings changed" in item.value for item in app.caption))
        app.button(key="prepare").click().run()
        self.assertNotEqual(old_id, app.session_state["bundle"][0])

    def test_upload_empty_state_is_actionable(self):
        app = self.app()
        app.radio(key="source").set_value("Upload images").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)
        self.assertTrue(any("Add a before and after image" in item.value for item in app.info))
        self.assertEqual(len(app.get("file_uploader")), 5)
