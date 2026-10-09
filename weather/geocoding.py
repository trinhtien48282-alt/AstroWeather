"""Open-Meteo place-name lookup. Stdlib only, no GUI."""
import urllib.parse

from weather.api import http_json

API_GEO = "https://geocoding-api.open-meteo.com/v1/search"


def geocode(name):
    q = {"name": name, "count": 6, "language": "en", "format": "json"}
    data = http_json(API_GEO + "?" + urllib.parse.urlencode(q))
    out = []
    for r in data.get("results", []) or []:
        label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
        out.append({"name": label, "lat": r["latitude"], "lon": r["longitude"]})
    return out
