
from pathlib import Path
import sys

# Allow running this script directly from the repository.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from astro.star_catalog_binary import (
    StarCatalogBinary,
    validate_against_json,
)

DATA = ROOT / "data"

catalogs = ("stars.6", "stars.8", "stars.14")
failed = False

for name in catalogs:
    json_path = DATA / f"{name}.json"
    binary_path = DATA / "binary" / f"{name}.awst"

    print(f"\nChecking {name}...")

    checked, errors = validate_against_json(
        binary_path,
        json_path,
    )

    with StarCatalogBinary(binary_path) as catalog:
        print(f"  Records: {len(catalog):,}")
        if len(catalog):
            print(f"  First record: {catalog[0]}")
            print(f"  Last record:  {catalog[-1]}")

    if errors:
        failed = True
        print(f"  FAILED: {errors} discrepancy(s)")
    else:
        print(f"  PASS: {checked:,} records verified")

if failed:
    raise SystemExit(1)

print("\nAll binary catalog checks passed.")
