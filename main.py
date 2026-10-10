#THIS IS THE MAIN CODE CLAUDE!
"""
ASTROWEATHER - observing forecast + telescope toolkit

  pip install customtkinter
  python astro_weather.py

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
import traceback

from config import log_error
from gui.app import AstroApp


def main():
    app = AstroApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error(traceback.format_exc())
        raise
