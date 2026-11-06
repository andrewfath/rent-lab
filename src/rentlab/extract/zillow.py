"""Zillow Observed Rent Index (ZORI) by ZIP, reshaped wide -> long."""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from rentlab import config
from rentlab.storage import partition_dir, write_records

DATE_COL = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def pull_zori(
    raw_dir: Path | None = None,
    session: requests.Session | None = None,
    today: date | None = None,
) -> Path:
    settings = config.sources_config()["zillow"]
    raw_dir = raw_dir or config.RAW_DIR
    session = session or requests.Session()
    today = today or datetime.now(UTC).date()

    resp = session.get(settings["zori_zip_url"], timeout=300)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    records = []
    for row in reader:
        if settings["metro_contains"] not in (row.get("Metro") or ""):
            continue
        for col, value in row.items():
            if DATE_COL.match(col) and value:
                records.append(
                    {
                        "zip_code": row["RegionName"].zfill(5),
                        "metro": row["Metro"],
                        "month": col,
                        "zori": float(value),
                    }
                )
    path = partition_dir(raw_dir, "zillow", "zori_zip", today) / "part-0000.parquet"
    return write_records(records, path)
