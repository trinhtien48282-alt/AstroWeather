"""Report invalid DSO source records and JSON-vs-binary counts. Prints ids and numbers only, never whole catalogues.
Run from the repo root:  python scripts/audit_catalogs.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from astro.dso_catalog_binary import DsoCatalogBinary  # noqa: E402

for name in ("dsos.6", "dsos.14", "dsos.bright", "messier", "lg"):
    src, binp = ROOT / "data" / f"{name}.json", ROOT / "data" / "binary" / f"{name}.awds"
    if not src.exists():
        continue
    feats = json.loads(src.read_text(encoding="utf-8")).get("features", [])
    bad = []
    for i, f in enumerate(feats):
        try:
            lon, dec = (float(v) for v in f["geometry"]["coordinates"][:2])
        except (KeyError, TypeError, ValueError):
            bad.append((i, f.get("id"), "unreadable coordinates"))
            continue
        if not (-180 <= lon <= 180 and -90 <= dec <= 90):
            p = f.get("properties") or {}
            bad.append((i, f.get("id"), f"lon={lon} dec={dec} desig={p.get('desig')!r} dim={p.get('dim')!r}"))
    n_bin = len(DsoCatalogBinary(binp)) if binp.exists() else None
    print(f"{name}: json {len(feats)}, invalid {len(bad)}, binary {n_bin}"
          + ("" if n_bin is None or n_bin == len(feats) - len(bad) else "  <-- COUNT MISMATCH"))
    for row in bad[:20]:
        print("   ", row)
