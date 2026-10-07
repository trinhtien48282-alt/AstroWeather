"""AstroWeather configuration: file locations, defaults, load/save and the error log.

Stdlib only. No GUI, no astronomy.
"""
import copy
import json
import os
from datetime import datetime

APP_NAME = "AstroWeather"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config"), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_PATH = os.path.join(CONFIG_DIR, "cache.json")
LOG_PATH = os.path.join(CONFIG_DIR, "error.log")

DEFAULT_CONFIG = {
    "location": {"name": "Ca Mau, Vietnam", "lat": 9.1769, "lon": 105.1524},
    "units": {"temp": "C", "wind": "km/h"},
    "bortle": 5,
    "auto_refresh_min": 30,
    "perf": {"numpy": True, "astropy": False},
    "planner": {"min_alt": 30, "kind": "All targets"},
    "camera": {"preset": "Custom"},
    "scope": {"name": "D76F700", "aperture": 76.0, "focal_length": 700.0, "obstruction_mm": 0.0, "mount": "AZ"},
    "eyepieces": [
        {"name": "20 mm", "fl": 20.0, "afov": 35.0},
        {"name": "12.5 mm", "fl": 12.5, "afov": 35.0},
        {"name": "4 mm", "fl": 4.0, "afov": 35.0},
    ],
    "barlows": [
        {"name": "1.5x Barlow", "factor": 1.5},
        {"name": "2x Barlow", "factor": 2.0},
    ],
}


def log_error(msg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        for key, default in DEFAULT_CONFIG.items():
            if key in loaded:
                if isinstance(default, dict) and isinstance(loaded[key], dict):
                    cfg[key].update(loaded[key])
                else:
                    cfg[key] = loaded[key]
    except FileNotFoundError:
        pass
    except Exception as e:
        log_error(f"config load failed: {e}")
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except Exception as e:
        log_error(f"config save failed: {e}")
