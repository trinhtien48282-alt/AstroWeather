
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OPTIMIZED_DIR = DATA_DIR / "optimized"
ARCHIVE_DIR = DATA_DIR / "archive"


def compact_json(data):
    """Remove unnecessary JSON formatting without changing its values."""
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def main():
    sources = sorted(
        path
        for path in DATA_DIR.rglob("*.json")
        if not (
            {"archive", "optimized"} & set(path.relative_to(DATA_DIR).parts)
        )
    )

    if not sources:
        print("No source JSON files found.")
        return

    total_original = 0
    total_compact = 0
    total_zip = 0
    failures = []

    print(f"Found {len(sources)} JSON files.\n")

    for source in sources:
        relative = source.relative_to(DATA_DIR)

        try:
            original_bytes = source.read_bytes()
            data = json.loads(original_bytes.decode("utf-8"))
            compact_bytes = compact_json(data)

            # Verify minification preserves the parsed data.
            if json.loads(compact_bytes.decode("utf-8")) != data:
                raise ValueError("JSON values changed during minification")

            output_json = OPTIMIZED_DIR / relative
            output_zip = ARCHIVE_DIR / relative.with_suffix(".zip")

            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_zip.parent.mkdir(parents=True, exist_ok=True)

            output_json.write_bytes(compact_bytes)

            # Archive the optimized JSON.
            with zipfile.ZipFile(
                output_zip,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                archive.writestr(relative.as_posix(), compact_bytes)

            # Verify ZIP integrity and archived content.
            with zipfile.ZipFile(output_zip, "r") as archive:
                bad_file = archive.testzip()
                if bad_file is not None:
                    raise RuntimeError(f"ZIP integrity failure: {bad_file}")

                archived_bytes = archive.read(relative.as_posix())
                archived_data = json.loads(
                    archived_bytes.decode("utf-8")
                )

            if archived_data != data:
                raise ValueError("Archived JSON does not match source")

            original_size = len(original_bytes)
            compact_size = len(compact_bytes)
            zip_size = output_zip.stat().st_size

            total_original += original_size
            total_compact += compact_size
            total_zip += zip_size

            print(
                f"{relative.as_posix()}\n"
                f"  Original: {original_size:>10,} bytes\n"
                f"  Compact:  {compact_size:>10,} bytes\n"
                f"  ZIP:      {zip_size:>10,} bytes"
            )

        except Exception as exc:
            failures.append((relative, str(exc)))
            print(f"FAILED: {relative}: {exc}")

    print("\n=== TOTALS ===")
    print(f"Files processed: {len(sources) - len(failures)}/{len(sources)}")
    print(f"Original:        {total_original:,} bytes")
    print(f"Compact JSON:    {total_compact:,} bytes")
    print(f"ZIP archives:    {total_zip:,} bytes")

    if total_original:
        print(
            f"Minification:    "
            f"{(1 - total_compact / total_original) * 100:.1f}% smaller"
        )
        print(
            f"ZIP vs original: "
            f"{(1 - total_zip / total_original) * 100:.1f}% smaller"
        )

    print(f"\nOptimized JSON: {OPTIMIZED_DIR}")
    print(f"ZIP archives:   {ARCHIVE_DIR}")

    if failures:
        print("\nSome files need attention:")
        for path, error in failures:
            print(f"  {path}: {error}")
        raise SystemExit(1)

    print("\nAll files verified successfully!")


if __name__ == "__main__":
    main()
