"""Landing raw records as Parquet.

Every extractor hands plain dicts to `write_records`. Nested objects are
flattened one level (`hoa.fee` -> `hoa__fee`); fields listed in `json_fields`,
and any remaining lists or deeper objects, are stored as JSON strings so a
schema surprise from an API never breaks the write. DuckDB parses them later.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


def flatten_record(
    record: dict[str, Any],
    json_fields: Iterable[str] = (),
    drop_fields: Iterable[str] = (),
) -> dict[str, Any]:
    json_fields = set(json_fields)
    drop_fields = set(drop_fields)
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key in drop_fields:
            continue
        if key in json_fields:
            out[key] = None if value is None else json.dumps(value, sort_keys=True)
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                out[f"{key}__{sub_key}"] = _scalar(sub_value)
        else:
            out[key] = _scalar(value)
    return out


def _scalar(value: Any) -> Any:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True)
    return value


def to_table(records: Sequence[dict[str, Any]], expected_fields: Iterable[str] = ()) -> pa.Table:
    """Build an Arrow table, guaranteeing `expected_fields` exist as columns."""
    columns: dict[str, None] = dict.fromkeys(expected_fields)
    for rec in records:
        columns.update(dict.fromkeys(rec))
    rows = [{col: rec.get(col) for col in columns} for rec in records]
    try:
        return pa.Table.from_pylist(rows)
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        # Mixed types in a column (e.g. 2 and "2A"): fall back to strings for those columns.
        arrays = {}
        for col in columns:
            values = [r[col] for r in rows]
            try:
                arrays[col] = pa.array(values)
            except (pa.ArrowInvalid, pa.ArrowTypeError):
                arrays[col] = pa.array([None if v is None else str(v) for v in values])
        return pa.table(arrays)


def partition_dir(raw_dir: Path, source: str, entity: str, pulled_at: date) -> Path:
    return raw_dir / source / entity / f"pulled_at={pulled_at.isoformat()}"


def write_records(
    records: Sequence[dict[str, Any]],
    path: Path,
    expected_fields: Iterable[str] = (),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = to_table(records, expected_fields)
    pq.write_table(table, path)
    return path
