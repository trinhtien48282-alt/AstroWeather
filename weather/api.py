"""Open-Meteo access: HTTP/JSON retrieval and the forecast + air-quality requests. Stdlib only, no GUI."""
import json
import urllib.error
import urllib.parse
import urllib.request

from config import log_error

API_FORECAST = "https://api.open-meteo.com/v1/forecast"
API_AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
BASE_VARS = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "surface_pressure",
             "precipitation_probability", "precipitation", "cloud_cover", "cloud_cover_low",
             "cloud_cover_mid", "cloud_cover_high", "visibility", "wind_speed_10m", "wind_direction_10m",
             "wind_gusts_10m", "cape"]
UPPER_VARS = ["wind_speed_250hPa", "wind_speed_300hPa"]


def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "AstroWeather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_weather(lat, lon):
    def url(vars_):
        q = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "hourly": ",".join(vars_),
             "timezone": "auto", "forecast_days": 5, "timeformat": "unixtime", "wind_speed_unit": "kmh"}
        return API_FORECAST + "?" + urllib.parse.urlencode(q, safe=",")

    try:
        wx = http_json(url(BASE_VARS + UPPER_VARS))
    except urllib.error.HTTPError:
        wx = http_json(url(BASE_VARS))  # upper-air winds not available: fall back
    aq = None
    try:
        q = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "timezone": "auto", "forecast_days": 5,
             "timeformat": "unixtime", "hourly": "pm10,pm2_5,aerosol_optical_depth,dust,us_aqi"}
        aq = http_json(API_AIR + "?" + urllib.parse.urlencode(q, safe=","))
    except Exception as e:
        log_error(f"air quality fetch failed: {e}")
    return wx, aq
