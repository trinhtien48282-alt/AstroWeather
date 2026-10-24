"""Sky-overlay settings: defaults and backward compatibility (stdlib unittest). Run: python -m unittest tests.test_config_sky -v"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402


class SkyConfigTests(unittest.TestCase):
    def load_with(self, content):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            if content is not None:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(content, f)
            old = config.CONFIG_PATH
            config.CONFIG_PATH = path
            try:
                return config.load_config()
            finally:
                config.CONFIG_PATH = old

    def test_defaults_are_off_and_independent(self):
        sky = self.load_with(None)["sky"]
        self.assertEqual(sky, {"constellation_lines": False, "constellation_names": False, "star_mag_limit": 5.0})

    def test_old_config_without_sky_key_gets_defaults_and_keeps_user_values(self):
        cfg = self.load_with({"bortle": 7, "units": {"temp": "F", "wind": "mph"}, "scope": {"aperture": 114.0}})
        self.assertEqual(cfg["sky"], {"constellation_lines": False, "constellation_names": False, "star_mag_limit": 5.0})
        self.assertEqual((cfg["bortle"], cfg["units"]["temp"], cfg["scope"]["aperture"]), (7, "F", 114.0))
        self.assertEqual(cfg["scope"]["focal_length"], 700.0)  # untouched default still filled in

    def test_partial_sky_dict_keeps_the_other_default(self):
        sky = self.load_with({"sky": {"constellation_lines": True}})["sky"]
        self.assertEqual(sky, {"constellation_lines": True, "constellation_names": False, "star_mag_limit": 5.0})

    def test_toggles_round_trip_through_save(self):
        with tempfile.TemporaryDirectory() as d:
            old = (config.CONFIG_DIR, config.CONFIG_PATH)
            config.CONFIG_DIR, config.CONFIG_PATH = d, os.path.join(d, "config.json")
            try:
                cfg = config.load_config()
                cfg["sky"]["constellation_names"] = True
                config.save_config(cfg)
                self.assertEqual(config.load_config()["sky"], {"constellation_lines": False, "constellation_names": True, "star_mag_limit": 5.0})
            finally:
                config.CONFIG_DIR, config.CONFIG_PATH = old


if __name__ == "__main__":
    unittest.main()
