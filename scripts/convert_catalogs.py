
#!/usr/bin/env python3
"""Convert AstroWeather star and DSO GeoJSON catalogs to binary.

Stars:
    AWST v1, 16-byte header, 28-byte records.
    Record: uint32 HIP ID, float64 RA, float64 Dec,
            float32 magnitude, float32 B-V.

Deep-sky objects:
    AWDS v1, 24-byte header, 74-byte records, UTF-8 string table.
    Record: seven uint32 string offsets, seven uint16 byte lengths,
            float64 RA, float64 Dec, float32 magnitude,
            float32 major dimension, float32 minor dimension,
            float32 B-V.

DSO string fields:
    feature_id, desig, type, morph, sub, pop, str

Missing DSO magnitude uses the source sentinel 999.
Missing dimensions and B-V are NaN.
DSOs with invalid coordinates are skipped with a warning.
Original JSON files are never modified.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

# Existing star format. Do not change these values.
STAR_MAGIC = b"AWST"
STAR_VERSION = 1
STAR_HEADER = struct.Struct("<4sHHQ")
STAR_RECORD = struct.Struct("<Iddff")

# DSO format.
DSO_MAGIC = b"AWDS"
DSO_VERSION = 1
DSO_HEADER = struct.Struct("<4sHHQQ")
DSO_RECORD = struct.Struct("<7I7Hddffff")

STRING_FIELDS = (
    "feature_id",
    "desig",
    "type",
    "morph",
    "sub",
    "pop",
    "str",
)


def number(
    value: Any,
    field: str,
    *,
    allow_missing: bool = False,
) -> float:
    """Parse a finite numeric value, optionally allowing missing values."""
    if value is None or value == "":
        if allow_missing:
            return math.nan
        raise ValueError(f"missing {field}")

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc

    if math.isnan(result) and allow_missing:
        return result
    if not math.isfinite(result):
        raise ValueError(f"non-finite {field}: {value!r}")

    return result


def parse_dimension(value: Any) -> tuple[float, float]:
    """Parse dimensions such as '110x90', in arcminutes."""
    if value is None or value == "":
        return math.nan, math.nan

    if isinstance(value, (int, float)):
        size = number(value, "dimension")
        if size < 0:
            raise ValueError(f"negative dimension: {value!r}")
        return size, size

    raw = str(value).strip().lower().replace(" ", "")
    parts = raw.split("x")

    if len(parts) == 1:
        size = number(parts[0], "dimension")
        if size < 0:
            raise ValueError(f"negative dimension: {value!r}")
        return size, size

    if len(parts) != 2:
        raise ValueError(f"invalid dimension: {value!r}")

    major = number(parts[0], "major dimension")
    minor = number(parts[1], "minor dimension")

    if major < 0 or minor < 0:
        raise ValueError(f"negative dimension: {value!r}")

    return major, minor


def text(value: Any, field: str) -> str:
    """Convert an optional scalar value to text."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        raise ValueError(f"{field} must be a scalar string")
    return str(value)


def coordinates(feature: dict[str, Any]) -> tuple[float, float]:
    """Convert GeoJSON longitude/latitude to RA/declination."""
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise ValueError("missing geometry")
    if geometry.get("type") != "Point":
        raise ValueError("expected Point geometry")

    coords = geometry.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise ValueError("expected coordinates [longitude, latitude]")

    lon = number(coords[0], "longitude")
    dec = number(coords[1], "declination")

    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude outside [-180, 180]: {lon}")
    if not -90.0 <= dec <= 90.0:
        raise ValueError(f"declination outside [-90, 90]: {dec}")

    return lon % 360.0, dec


def properties_of(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties")
    if props is None:
        return {}
    if not isinstance(props, dict):
        raise ValueError("properties must be an object")
    return props


def detect_kind(features: list[Any]) -> str:
    """Detect DSO catalogs by DSO-specific properties."""
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        if isinstance(props, dict) and any(
            key in props
            for key in ("desig", "morph", "dim", "sub", "pop", "str")
        ):
            return "dso"
    return "star"


def encode_star(feature: Any, index: int) -> bytes:
    try:
        if not isinstance(feature, dict):
            raise ValueError("feature must be an object")
        if feature.get("type") != "Feature":
            raise ValueError("expected type='Feature'")

        try:
            hip = int(str(feature.get("id", "")).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid or missing HIP identifier") from exc

        if not 0 <= hip <= 0xFFFFFFFF:
            raise ValueError(f"HIP ID outside uint32 range: {hip}")

        ra, dec = coordinates(feature)
        props = properties_of(feature)
        mag = number(props.get("mag"), "magnitude")
        bv = number(props.get("bv"), "B-V", allow_missing=True)

        return STAR_RECORD.pack(hip, ra, dec, mag, bv)
    except (ValueError, struct.error, OverflowError) as exc:
        raise ValueError(f"feature {index}: {exc}") from exc


def encode_dso(
    feature: Any,
    index: int,
    string_table: bytearray,
) -> bytes:
    """Encode one DSO record and append its strings to the string table."""
    try:
        if not isinstance(feature, dict):
            raise ValueError("feature must be an object")
        if feature.get("type") != "Feature":
            raise ValueError("expected type='Feature'")

        # Validate coordinates before mutating the shared string table.
        ra, dec = coordinates(feature)
        props = properties_of(feature)

        values = {
            "feature_id": text(feature.get("id"), "feature.id"),
            "desig": text(props.get("desig"), "desig"),
            "type": text(props.get("type"), "type"),
            "morph": text(props.get("morph"), "morph"),
            "sub": text(props.get("sub"), "sub"),
            "pop": text(props.get("pop"), "pop"),
            "str": text(props.get("str"), "str"),
        }

        if not values["feature_id"]:
            values["feature_id"] = values["desig"]
        if not values["desig"]:
            values["desig"] = values["feature_id"]
        if not values["desig"]:
            raise ValueError("missing both feature.id and properties.desig")

        # Validate all numeric fields before appending strings.
        mag = number(
            props.get("mag"), "magnitude", allow_missing=True
        )
        if math.isnan(mag):
            mag = 999.0

        dim_major, dim_minor = parse_dimension(props.get("dim"))
        bv = number(props.get("bv"), "B-V", allow_missing=True)

        offsets: list[int] = []
        lengths: list[int] = []
        encoded_values: list[bytes] = []

        for field in STRING_FIELDS:
            encoded = values[field].encode("utf-8")
            if len(encoded) > 0xFFFF:
                raise ValueError(f"{field} exceeds 65535 UTF-8 bytes")
            encoded_values.append(encoded)

        for encoded in encoded_values:
            if len(string_table) > 0xFFFFFFFF:
                raise ValueError("string table exceeds uint32 offsets")
            offsets.append(len(string_table))
            lengths.append(len(encoded))
            string_table.extend(encoded)

        return DSO_RECORD.pack(
            *offsets,
            *lengths,
            ra,
            dec,
            mag,
            dim_major,
            dim_minor,
            bv,
        )
    except (ValueError, struct.error, OverflowError) as exc:
        raise ValueError(f"feature {index}: {exc}") from exc


def read_document(source: Path) -> tuple[dict[str, Any], list[Any]]:
    with source.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    if not isinstance(document, dict):
        raise ValueError("root JSON value must be an object")
    if document.get("type") != "FeatureCollection":
        raise ValueError("expected GeoJSON FeatureCollection")

    features = document.get("features")
    if not isinstance(features, list):
        raise ValueError("'features' must be a list")

    return document, features


def convert(source: Path, destination: Path, kind: str) -> tuple[int, int]:
    """Write a validated binary file and publish it atomically."""
    if kind not in ("star", "dso"):
        raise ValueError(f"unsupported catalog kind: {kind}")
    if not source.is_file():
        raise FileNotFoundError(f"input file not found: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("output must not overwrite the source file")

    _, features = read_document(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    string_table = bytearray()
    written_count = 0
    skipped_count = 0
    temp_name: str | None = None

    header_struct = STAR_HEADER if kind == "star" else DSO_HEADER
    record_struct = STAR_RECORD if kind == "star" else DSO_RECORD
    magic = STAR_MAGIC if kind == "star" else DSO_MAGIC
    version = STAR_VERSION if kind == "star" else DSO_VERSION

    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=destination.parent,
            prefix=destination.name + ".",
            suffix=".tmp",
            delete=False,
        ) as output:
            temp_name = output.name

            # Reserve space for the final header.
            output.write(b"\0" * header_struct.size)

            if kind == "star":
                for index, feature in enumerate(features):
                    output.write(encode_star(feature, index))
                    written_count += 1
            else:
                for index, feature in enumerate(features):
                    try:
                        # Skip only coordinate-invalid DSOs. Other malformed
                        # records remain hard errors, not silent data loss.
                        if not isinstance(feature, dict):
                            raise ValueError("feature must be an object")
                        coordinates(feature)
                        record = encode_dso(feature, index, string_table)
                    except ValueError as exc:
                        message = str(exc)
                        if (
                            "declination outside [-90, 90]" in message
                            or "longitude outside [-180, 180]" in message
                        ):
                            print(
                                f"WARN {source}: skipping invalid coordinates: "
                                f"{message}",
                                file=sys.stderr,
                            )
                            skipped_count += 1
                            continue
                        raise

                    output.write(record)
                    written_count += 1

                # Append the string table ONCE, after all records.
                output.write(string_table)

            if kind == "star":
                header = STAR_HEADER.pack(
                    magic, version, record_struct.size, written_count
                )
            else:
                header = DSO_HEADER.pack(
                    magic,
                    version,
                    record_struct.size,
                    written_count,
                    len(string_table),
                )

            output.seek(0)
            output.write(header)
            output.flush()
            os.fsync(output.fileno())

        expected_size = (
            header_struct.size
            + written_count * record_struct.size
            + (len(string_table) if kind == "dso" else 0)
        )
        actual_size = Path(temp_name).stat().st_size
        if actual_size != expected_size:
            raise RuntimeError(
                f"size verification failed: expected {expected_size}, "
                f"got {actual_size}"
            )

        with open(temp_name, "rb") as check:
            header_data = check.read(header_struct.size)

        if kind == "star":
            check_magic, check_version, check_record_size, check_count = (
                STAR_HEADER.unpack(header_data)
            )
            valid = (
                check_magic == STAR_MAGIC
                and check_version == STAR_VERSION
                and check_record_size == STAR_RECORD.size
                and check_count == written_count
            )
        else:
            (
                check_magic,
                check_version,
                check_record_size,
                check_count,
                check_table_size,
            ) = DSO_HEADER.unpack(header_data)
            valid = (
                check_magic == DSO_MAGIC
                and check_version == DSO_VERSION
                and check_record_size == DSO_RECORD.size
                and check_count == written_count
                and check_table_size == len(string_table)
            )

        if not valid:
            raise RuntimeError("binary header verification failed")

        os.replace(temp_name, destination)
        temp_name = None

    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)

    if skipped_count:
        print(f"    Skipped invalid-coordinate DSOs: {skipped_count:,}")

    return written_count, destination.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert AstroWeather star and DSO GeoJSON catalogs."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Input GeoJSON files. Defaults to the standard catalog set.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/binary"),
        help="Output directory (default: data/binary)",
    )
    parser.add_argument(
        "--kind",
        choices=("auto", "star", "dso"),
        default="auto",
        help="Force a format, or detect it automatically.",
    )
    args = parser.parse_args()

    inputs = args.inputs or [
        Path("data/stars.6.json"),
        Path("data/stars.8.json"),
        Path("data/stars.14.json"),
        Path("data/dsos.6.json"),
        Path("data/dsos.14.json"),
        Path("data/dsos.bright.json"),
        Path("data/messier.json"),
        Path("data/lg.json"),
    ]

    failures = 0

    for source in inputs:
        try:
            _, features = read_document(source)
            kind = args.kind if args.kind != "auto" else detect_kind(features)
            suffix = ".awst" if kind == "star" else ".awds"
            destination = args.output_dir / f"{source.stem}{suffix}"

            count, size = convert(source, destination, kind)
            record_size = STAR_RECORD.size if kind == "star" else DSO_RECORD.size
            header_size = STAR_HEADER.size if kind == "star" else DSO_HEADER.size

            print(f"OK  {source} -> {destination}")
            print(f"    Kind: {kind}")
            print(f"    Records: {count:,}")
            print(f"    Binary size: {size:,} bytes")
            print(
                f"    Record size: {record_size} bytes; "
                f"header size: {header_size} bytes"
            )

        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            RuntimeError,
            struct.error,
            OverflowError,
        ) as exc:
            failures += 1
            print(f"ERR {source}: {exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
