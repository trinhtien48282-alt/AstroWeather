
import json
from pathlib import Path
from collections import Counter

CATALOG_PATH = Path("data/starnames.json")

with CATALOG_PATH.open("r", encoding="utf-8") as f:
    catalog = json.load(f)

print("Top-level type:", type(catalog).__name__)

if isinstance(catalog, dict):
    print("Record count:", len(catalog))
    print("Top-level sample keys:", list(catalog)[:5])

    field_counts = Counter()
    samples = []

    for hip, record in catalog.items():
        if isinstance(record, dict):
            field_counts.update(record.keys())

            # Keep only a few representative records.
            if len(samples) < 5:
                samples.append({hip: record})

    print("\nFields:")
    for field, count in field_counts.most_common():
        print(f"  {field}: {count}/{len(catalog)} records")

    print("\nSample records:")
    print(json.dumps(samples, ensure_ascii=False, indent=2))
