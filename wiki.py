"""Wikipedia page summaries for the sky chart's object info (REST API, no key). Stdlib only, no GUI."""
import urllib.error
import urllib.parse

from weather.api import http_json

API_WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary/"
MAX_CHARS = 900


def summary(titles):
    """First usable article among the candidate titles -> {"title", "extract", "url"}, or None when none exists.
    Network errors propagate to the caller."""
    for t in titles:
        try:
            d = http_json(API_WIKI + urllib.parse.quote(t.replace(" ", "_"), safe="()"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        text = (d.get("extract") or "").strip()
        if d.get("type") == "disambiguation" or not text:
            continue
        if len(text) > MAX_CHARS:
            cut = text.rfind(". ", 0, MAX_CHARS)
            text = text[:cut + 1] if cut > 200 else text[:MAX_CHARS].rstrip() + "..."
        url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
        return {"title": d.get("title") or t, "extract": text, "url": url}
    return None
