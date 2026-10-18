
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "starnames.json"
OUTPUT_DIR = ROOT / "data" / "optimized"
JSON_OUTPUT = OUTPUT_DIR / "starnames.en.json"
ZIP_OUTPUT = ROOT / "data" / "archive" / "starnames.en.zip"

# Keep English (if present), primary names, and astronomical identifiers.
LANGUAGE_FIELDS = {
    "ar", "de", "el", "es", "fa", "fi", "fr", "he",
    "hi", "it", "ja", "ko", "la", "ru", "tr", "zh",
}


def compact_catalog(data):
    result = {}

    for record_id, record in data.items():
        if not isinstance(record, dict):
            result[record_id] = record
            continue

        result[record_id] = {
            key: value
            for key, value in record.items()
            if value != "" and key not in LANGUAGE_FIELDS
        }

    return result


def main():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Source catalog not found: {SOURCE}")

    original_bytes = SOURCE.stat().st_size
    original = json.loads(SOURCE.read_text(encoding="utf-8"))
    optimized = compact_catalog(original)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ZIP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    JSON_OUTPUT.write_text(
        json.dumps(optimized, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # Verify the generated JSON preserves all record IDs and retained values.
    reloaded = json.loads(JSON_OUTPUT.read_text(encoding="utf-8"))
    assert reloaded.keys() == original.keys(), "Record IDs changed!"
    assert reloaded == optimized, "Generated JSON does not match!"

    with zipfile.ZipFile(
        ZIP_OUTPUT, "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.write(JSON_OUTPUT, arcname="starnames.en.json")

    # Verify archive integrity and its JSON contents.
    with zipfile.ZipFile(ZIP_OUTPUT, "r") as archive:
        bad_file = archive.testzip()
        if bad_file is not None:
            raise RuntimeError(f"ZIP integrity check failed: {bad_file}")

        archived_data = json.loads(
            archive.read("starnames.en.json").decode("utf-8")
        )

    assert archived_data == optimized, "Archived JSON differs from output!"

    json_size = JSON_OUTPUT.stat().st_size
    zip_size = ZIP_OUTPUT.stat().st_size

    print("=== CATALOG GENERATION SUCCESS ===")
    print(f"Records:       {len(original):,} -> {len(optimized):,}")
    print(f"Original JSON: {original_bytes:,} bytes")
    print(f"Optimized:     {json_size:,} bytes")
    print(f"ZIP archive:   {zip_size:,} bytes")
    print(f"JSON reduction: {(1 - json_size / original_bytes) * 100:.1f}%")
    print(f"ZIP reduction:  {(1 - zip_size / original_bytes) * 100:.1f}%")
    print(f"JSON: {JSON_OUTPUT.relative_to(ROOT)}")
    print(f"ZIP:  {ZIP_OUTPUT.relative_to(ROOT)}")
    print("Verification: PASSED")


if __name__ == "__main__":
    main()
