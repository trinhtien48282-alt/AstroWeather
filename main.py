
"""
ASTROWEATHER - observing forecast + telescope toolkit

  python -m pip install -r requirements.txt
  python main.py

Pages
  Tonight    deep-sky and planetary scores, best window, insights, planets, targets
  Forecast   hour-by-hour heat map: light, moon, 3 cloud layers, rain, transparency,
             seeing, wind, gusts, humidity, dew margin, temperature, scores
  Planner    rank targets over a date/time range, with reasons, eyepiece advice and an altitude graph
  Sky        live alt-az sky chart with a time slider (sun, moon, planets, stars, deep sky)
  Telescope  specs, eyepiece table, magnification / field / arcs / resolution /
             drift-time calculators and a camera (imaging) calculator
  Settings   location search, units, light pollution (Bortle), your gear

Data: Open-Meteo (free, no API key) for weather + air quality. Sun, Moon, planets and
sky positions are computed locally (no internet needed for those).
Honest note: no free service gives a true "seeing" forecast, so Seeing and
Transparency here are scientifically-motivated proxies (jet-stream wind, ground wind,
thermal change, CAPE / aerosols, humidity, visibility). See Settings > How scores work.
"""
import sys
import traceback

from PySide6.QtWidgets import QApplication

if sys.version_info < (3, 12):  # the GUI code uses 3.12-only f-string syntax
    sys.exit("AstroWeather needs Python 3.12 or newer.")

from config import log_error
from gui.app import AstroApp


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = AstroApp()
    window.show()
    return app.exec()


def _qt_exception_hook(exc_type, exc, tb):
    log_error("".join(traceback.format_exception(exc_type, exc, tb)))
    sys.__excepthook__(exc_type, exc, tb)


if __name__ == "__main__":
    sys.excepthook = _qt_exception_hook
    try:
        main()
    except Exception:
        log_error(traceback.format_exc())
        raise
