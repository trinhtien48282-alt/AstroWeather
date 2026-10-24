
"""Reader for AstroWeather's AWST binary star catalogs.

Format v1:
    Header: <4sHHQ
    Record: <Iddff

Record fields:
    hip_id, ra_degrees, dec_degrees, magnitude, bv_color_index

This module uses only the Python standard library.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

MAGIC = b"AWST"
VERSION = 1

HEADER = struct.Struct("<4sHHQ")
RECORD = struct.Struct("<Iddff")


@dataclass(frozen=True, slots=True)
class StarRecord:
    hip_id: int
    ra: float
    dec: float
    magnitude: float
    bv: float

    @property
    def has_bv(self) -> bool:
        return math.isfinite(self.bv)


class StarCatalogBinary:
    """Validated reader with iteration and indexed record access."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._file = self.path.open("rb")

        try:
            raw_header = self._file.read(HEADER.size)
            if len(raw_header) != HEADER.size:
                raise ValueError("Truncated AWST header")

            magic, version, record_size, count = HEADER.unpack(raw_header)

            if magic != MAGIC:
                raise ValueError("Not an AWST star catalog")
            if version != VERSION:
                raise ValueError(
                    f"Unsupported AWST version: {version}"
                )
            if record_size != RECORD.size:
                raise ValueError(
                    f"Unexpected record size: {record_size}"
                )

            expected_size = HEADER.size + count * RECORD.size
            actual_size = self.path.stat().st_size

            if actual_size != expected_size:
                raise ValueError(
                    f"Catalog size mismatch: expected {expected_size}, "
                    f"found {actual_size}"
                )

            self.count = count
            self.record_size = record_size
            self._data_offset = HEADER.size

        except Exception:
            self._file.close()
            raise

    def __enter__(self) -> "StarCatalogBinary":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __len__(self) -> int:
        return self.count

    def _check_index(self, index: int) -> int:
        if not isinstance(index, int):
            raise TypeError("Star index must be an integer")
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError("Star index out of range")
        return index

    def get(self, index: int) -> StarRecord:
        """Read one record by zero-based catalog position."""
        index = self._check_index(index)
        offset = self._data_offset + index * self.record_size

        self._file.seek(offset)
        raw = self._file.read(self.record_size)

        if len(raw) != self.record_size:
            raise ValueError(f"Truncated record at index {index}")

        return StarRecord(*RECORD.unpack(raw))

    def __getitem__(self, index: int) -> StarRecord:
        if isinstance(index, slice):
            start, stop, step = index.indices(self.count)
            return [self.get(i) for i in range(start, stop, step)]
        return self.get(index)

    def __iter__(self) -> Iterator[StarRecord]:
        """Sequentially read records from the beginning."""
        self._file.seek(self._data_offset)

        for index in range(self.count):
            raw = self._file.read(self.record_size)
            if len(raw) != self.record_size:
                raise ValueError(f"Truncated record at index {index}")
            yield StarRecord(*RECORD.unpack(raw))


def json_star_records(path: str | Path) -> Iterator[StarRecord]:
    """Yield equivalent records from the source GeoJSON for validation."""
    path = Path(path)

    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    if document.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection")

    for index, feature in enumerate(document.get("features", [])):
        try:
            hip_id = int(str(feature["id"]).strip())
            longitude, dec = feature["geometry"]["coordinates"][:2]
            ra = float(longitude) % 360.0
            dec = float(dec)

            properties = feature.get("properties") or {}
            magnitude = float(properties["mag"])

            bv_value = properties.get("bv")
            bv = (
                math.nan
                if bv_value is None or bv_value == ""
                else float(bv_value)
            )

            yield StarRecord(
                hip_id=hip_id,
                ra=ra,
                dec=dec,
                magnitude=magnitude,
                bv=bv,
            )

        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid source JSON feature {index}: {exc}"
            ) from exc


def validate_against_json(
    binary_path: str | Path,
    json_path: str | Path,
) -> tuple[int, int]:
    """Compare records in order. Returns (records_checked, failures)."""
    checked = 0
    failures = 0

    with StarCatalogBinary(binary_path) as catalog:
        for index, source in enumerate(json_star_records(json_path)):
            if index >= len(catalog):
                print(f"FAIL: JSON contains extra record at index {index}")
                failures += 1
                break

            binary = catalog[index]
            checked += 1

            # Float32 fields are expected to differ slightly from JSON floats.
            if binary.hip_id != source.hip_id:
                print(f"FAIL index {index}: HIP ID differs")
                failures += 1
            if not math.isclose(binary.ra, source.ra, abs_tol=1e-10):
                print(f"FAIL index {index}: RA differs")
                failures += 1
            if not math.isclose(binary.dec, source.dec, abs_tol=1e-10):
                print(f"FAIL index {index}: declination differs")
                failures += 1
            if not math.isclose(
                binary.magnitude, source.magnitude,
                rel_tol=1e-6, abs_tol=1e-6
            ):
                print(f"FAIL index {index}: magnitude differs")
                failures += 1

            if math.isnan(source.bv):
                if not math.isnan(binary.bv):
                    print(f"FAIL index {index}: missing B-V not preserved")
                    failures += 1
            elif not math.isclose(
                binary.bv, source.bv,
                rel_tol=1e-6, abs_tol=1e-6
            ):
                print(f"FAIL index {index}: B-V differs")
                failures += 1

        if checked != len(catalog):
            print(
                f"FAIL: binary has {len(catalog)} records, "
                f"JSON yielded {checked}"
            )
            failures += 1

    return checked, failures
