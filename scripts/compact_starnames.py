
import json
from pathlib import Path

source = Path("data/starnames.json")
output = Path("data/starnames.compact.json")

with source.open("r", encoding="utf-8") as f:
    original = json.load(f)

# Preserve every record and every non-empty value.
compact = {
    hip: {
        key: value
        for key, value in record.items()
        if value != ""
    } if isinstance(record, dict) else record
    for hip, record in original.items()
}

with output.open("w", encoding="utf-8") as f:
    json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

before = source.stat().st_size
after = output.stat().st_size

print(f"Original: {before:,} bytes")
print(f"Compact:  {after:,} bytes")
print(f"Saved:    {before - after:,} bytes")
print(f"Reduced:  {(before-after)/before*100:.1f}%")
print(f"Output:   {output}")
print(f"Records:  {len(original):,} -> {len(compact):,}")
