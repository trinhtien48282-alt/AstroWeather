
import gzip
import json
import statistics
import time
from pathlib import Path

ORIGINAL = Path("data/starnames.json")
COMPACT = Path("data/starnames.compact.json")
RUNS = 30


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def benchmark(path):
    # Warm-up, so initial filesystem effects are less dominant.
    load_json(path)
    timings = []

    for _ in range(RUNS):
        start = time.perf_counter()
        load_json(path)
        timings.append((time.perf_counter() - start) * 1000)

    return statistics.median(timings)


def nonempty_pairs(data):
    """Represent all non-empty field values without depending on key order."""
    return {
        (record_id, key): value
        for record_id, record in data.items()
        if isinstance(record, dict)
        for key, value in record.items()
        if value != ""
    }


def main():
    original = load_json(ORIGINAL)
    compact = load_json(COMPACT)

    print("=== FILE SIZE ===")
    for path in (ORIGINAL, COMPACT):
        raw = path.read_bytes()
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        print(f"{path}: {len(raw):,} bytes")
        print(f"  gzip: {len(compressed):,} bytes")

    print("\n=== DATA PRESERVATION ===")
    print(f"Original records: {len(original):,}")
    print(f"Compact records:  {len(compact):,}")
    print(f"Same record IDs:  {original.keys() == compact.keys()}")

    before = nonempty_pairs(original)
    after = nonempty_pairs(compact)
    print(f"Non-empty values preserved: {before == after}")
    print(f"Original non-empty fields: {len(before):,}")
    print(f"Compact non-empty fields:  {len(after):,}")

    print("\n=== JSON LOAD BENCHMARK ===")
    for path in (ORIGINAL, COMPACT):
        print(f"{path}: median {benchmark(path):.3f} ms ({RUNS} runs)")


if __name__ == "__main__":
    main()
