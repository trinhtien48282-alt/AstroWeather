"""Reader for AstroWeather's AWDS v1 binary deep-sky catalogues (stdlib only).

Layout (see scripts/convert_catalogs.py):
    Header: <4sHHQQ  (24 bytes): magic, version, record size, record count, string-table size
    Record: <7I7Hddffff (74 bytes): 7 string offsets, 7 string byte-lengths, ra, dec, mag, dim_major, dim_minor, bv
    Then the UTF-8 string table. Offsets are relative to the table start; lengths are UTF-8 BYTES.
String fields, in order: feature_id, desig, type, morph, sub, pop, str (exposed as `stream`).
Missing: mag 999.0, dimensions and bv NaN.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

MAGIC = b"AWDS"
VERSION = 1
HEADER = struct.Struct("<4sHHQQ")
RECORD = struct.Struct("<7I7Hddffff")
STRING_FIELDS = ("feature_id", "desig", "type", "morph", "sub", "pop", "str")
NO_MAG = 999.0


@dataclass(frozen=True, slots=True)
class DsoRecord:
    feature_id: str
    desig: str
    type: str
    morph: str
    sub: str
    pop: str
    stream: str
    ra: float
    dec: float
    mag: float
    dim_major: float
    dim_minor: float
    bv: float

    @property
    def has_mag(self) -> bool:
        return math.isfinite(self.mag) and self.mag < NO_MAG - 0.5  # 999 means "unknown", not "very faint"

    @property
    def has_dim(self) -> bool:
        return math.isfinite(self.dim_major)


class DsoCatalogBinary:
    """Validated reader: the header and file length are checked on open, every string range on access."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        data = self.path.read_bytes()
        if len(data) < HEADER.size:
            raise ValueError("Truncated AWDS header")
        magic, version, record_size, count, table_size = HEADER.unpack_from(data)
        if magic != MAGIC:
            raise ValueError("Not an AWDS deep-sky catalog")
        if version != VERSION:
            raise ValueError(f"Unsupported AWDS version: {version}")
        if record_size != RECORD.size:
            raise ValueError(f"Unexpected record size: {record_size}")
        expected = HEADER.size + count * RECORD.size + table_size
        if len(data) != expected:
            raise ValueError(f"Catalog size mismatch: expected {expected}, found {len(data)}")
        self._data, self.count, self._table_size = data, count, table_size
        self._table = HEADER.size + count * RECORD.size

    def __len__(self) -> int:
        return self.count

    def get(self, index: int) -> DsoRecord:
        if not isinstance(index, int):
            raise TypeError("DSO index must be an integer")
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError("DSO index out of range")
        v = RECORD.unpack_from(self._data, HEADER.size + index * RECORD.size)
        strings = []
        for name, off, ln in zip(STRING_FIELDS, v[:7], v[7:14]):
            if off + ln > self._table_size:
                raise ValueError(f"record {index}: {name} range [{off}, {off + ln}) outside the {self._table_size}-byte string table")
            raw = self._data[self._table + off:self._table + off + ln]
            try:
                strings.append(raw.decode("utf-8"))
            except UnicodeDecodeError as e:
                raise ValueError(f"record {index}: {name} is not valid UTF-8 ({e})") from e
        return DsoRecord(*strings, *v[14:])

    __getitem__ = get

    def __iter__(self) -> Iterator[DsoRecord]:
        for i in range(self.count):
            yield self.get(i)
