
import json
from pathlib import Path

source = Path("data/starnames.json")  # Change this!
output = source.with_name(source.stem + ".min.json")

with source.open("r", encoding="utf-8") as f:
    data = json.load(f)

with output.open("w", encoding="utf-8", newline="\n") as f:
    json.dump(
        data,
        f,
        ensure_ascii=False,
        separators=(",", ":"),
    )

before = source.stat().st_size
after = output.stat().st_size

print(f"Original: {before:,} bytes")
print(f"Minified: {after:,} bytes")
print(f"Saved: {before - after:,} bytes ({(before-after)/before*100:.1f}%)")
print(f"Output: {output}")
