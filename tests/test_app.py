import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
from streamlit.testing.v1 import AppTest

from app import run_analysis
from change_watch.satellite import NoClearPair, SatelliteRequest, find_pair

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
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        return app.radio(key="source").set_value("Synthetic demo").run()

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


class SatelliteInterfaceTests(unittest.TestCase):
    def app(self, region=False):
        from test_satellite import AOI

        app = AppTest.from_file(str(APP), default_timeout=30)
        if region:
            app.session_state["satellite_aoi"] = AOI
        return app.run()

    def load_pair(self):
        from test_satellite import AOI, Catalogue, reader, scene

        pair = find_pair(
            SatelliteRequest(AOI, date(2025, 6, 1), date(2025, 6, 30), 0),
            client=Catalogue([scene("before", 1), scene("after", 30)]),
            reader=reader,
        )
        app = self.app(region=True)
        app.date_input(key="satellite_start").set_value(date(2025, 6, 1))
        app.date_input(key="satellite_end").set_value(date(2025, 6, 30))
        app.selectbox(key="satellite_window").set_value(0).run()
        with patch("change_watch.satellite_ui.find_pair", return_value=pair) as fetch:
            app.button(key="satellite_fetch").click().run()
            fetch.assert_called_once()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 4)
        return app, pair

    def test_default_map_shows_calendars_and_requires_a_region(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key="source").value, "Satellite map")
        self.assertEqual(len(app.date_input), 2)
        self.assertTrue(app.checkbox(key="satellite_strict").value)
        self.assertFalse(app.metric)
        self.assertTrue(any("Draw a region" in item.value for item in app.info))

    def test_invalid_dates_are_reported_before_network_access(self):
        app = self.app(region=True)
        app.date_input(key="satellite_start").set_value(date(2025, 7, 1))
        app.date_input(key="satellite_end").set_value(date(2025, 6, 1)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Start must precede end" in item.value for item in app.error))
        self.assertFalse(app.metric)

    def test_drawing_edits_keep_the_map_component_identity(self):
        from shapely.geometry import box, mapping
        from test_satellite import AOI

        app = self.app()
        first = {"type": "Feature", "properties": {}, "geometry": AOI}
        changed = mapping(box(69.25, 53.2, 69.265, 53.215))
        edited = {"type": "Feature", "properties": {}, "geometry": changed}
        with patch(
            "change_watch.satellite_ui.draw_map", return_value={"all_drawings": [first]}
        ) as render:
            app.run()
            self.assertIsNone(render.call_args.args[0])
        epoch = app.session_state["satellite_map_epoch"]
        with patch(
            "change_watch.satellite_ui.draw_map", return_value={"all_drawings": [edited]}
        ) as render:
            app.run()
            self.assertIsNone(render.call_args.args[0])
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["satellite_map_epoch"], epoch)
        self.assertEqual(
            app.session_state["satellite_aoi"]["coordinates"][0][0],
            list(changed["coordinates"][0][0]),
        )
        with patch("change_watch.satellite_ui.draw_map", return_value={"all_drawings": []}):
            app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Draw a region" in item.value for item in app.info))

    def test_returning_to_map_mode_restores_the_current_region(self):
        app = self.app(region=True)
        region = app.session_state["satellite_aoi"]
        app.radio(key="source").set_value("Synthetic demo").run()
        with patch(
            "change_watch.satellite_ui.draw_map", return_value={"all_drawings": None}
        ) as render:
            app.radio(key="source").set_value("Satellite map").run()
            self.assertEqual(render.call_args.args[0], region)
        self.assertFalse(app.exception)

    def test_changing_dates_or_quality_invalidates_the_loaded_pair(self):
        for kind in ("date", "quality"):
            with self.subTest(kind=kind):
                app, _ = self.load_pair()
                if kind == "date":
                    app.date_input(key="satellite_end").set_value(date(2025, 7, 1)).run()
                else:
                    app.slider(key="satellite_scene_cloud").set_value(10).run()
                self.assertFalse(app.exception)
                self.assertFalse(app.metric)
                self.assertTrue(any("settings changed" in item.value for item in app.info))

    def test_clear_region_removes_old_imagery(self):
        app, _ = self.load_pair()
        app.button(key="satellite_clear").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)
        self.assertNotIn("satellite_pair", app.session_state)

    def test_failed_refresh_does_not_reuse_a_successful_pair(self):
        app, _ = self.load_pair()
        error = NoClearPair(
            "No qualifying pair found", [{"status": "Region quality limits exceeded"}]
        )
        with patch("change_watch.satellite_ui.find_pair", side_effect=error):
            app.button(key="satellite_fetch").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)
        self.assertTrue(any("No qualifying pair" in item.value for item in app.error))

    def test_bundle_includes_geographic_inputs_and_cloud_checks(self):
        import io
        import zipfile

        app, _ = self.load_pair()
        app.button(key="prepare").click().run()
        self.assertFalse(app.exception)
        with zipfile.ZipFile(io.BytesIO(app.session_state["bundle"][1])) as archive:
            self.assertIn("aoi.geojson", archive.namelist())
            self.assertIn("before_scl.tif", archive.namelist())
            self.assertIn("change_mask_georeferenced.tif", archive.namelist())
            self.assertIn("satellite_provenance.json", archive.namelist())
