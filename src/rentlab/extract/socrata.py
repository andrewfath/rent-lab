"""Generic Socrata (SODA) extractor for Cook County and City of Chicago datasets.

Datasets are declared in config/sources.yml; this module only knows how to page.

Robustness rules:
* Slow pages are retried, and after a timeout the page size is halved, because
  big filtered datasets (crimes) can take minutes to serve 50,000 rows.
* Pages are written to data/_incomplete/ first and moved into data/raw/ only when
  the whole dataset has arrived, so a failed pull never leaves half a dataset
  where dbt would read it, and never deletes the last good pull.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import requests

from rentlab import config
from rentlab.storage import flatten_record, partition_dir, write_records

MIN_PAGE_SIZE = 1000
RETRYABLE_STATUS = (429, 500, 502, 503, 504)


class SocrataError(RuntimeError):
    pass


@dataclass
class SocrataResult:
    dataset: str
    rows: int = 0
    files: list[Path] = field(default_factory=list)
    page_size_used: int = 0


def dataset_names() -> list[str]:
    return list(config.sources_config()["socrata"]["datasets"])


def build_params(spec: dict[str, Any], assessor_year: int, limit: int, offset: int) -> dict:
    params: dict[str, Any] = {
        "$select": ", ".join(spec["select"]),
        "$order": ":id",
        "$limit": limit,
        "$offset": offset,
    }
    if spec.get("where"):
        params["$where"] = spec["where"].format(assessor_year=assessor_year)
    return params


def _source_entity(name: str) -> tuple[str, str]:
    prefix, _, entity = name.partition("_")
    return ("cook_county" if prefix == "cook" else "chicago_portal"), entity


def pull_dataset(
    name: str,
    raw_dir: Path | None = None,
    session: requests.Session | None = None,
    max_pages: int | None = None,
    today: date | None = None,
    progress: Any = None,
) -> SocrataResult:
    settings = config.sources_config()["socrata"]
    spec = settings["datasets"][name]
    raw_dir = raw_dir or config.RAW_DIR
    session = session or requests.Session()
    today = today or datetime.now(UTC).date()
    limit = int(spec.get("page_size", settings["page_size"]))
    timeout = int(settings.get("read_timeout_seconds", 300))
    url = f"https://{spec['domain']}/resource/{spec['dataset_id']}.json"
    headers = {}
    if token := os.environ.get("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = token

    source, entity = _source_entity(name)
    final_dir = partition_dir(raw_dir, source, entity, today)
    work_dir = partition_dir(raw_dir.parent / "_incomplete", source, entity, today)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    expected = [c for c in spec["select"] if c != "location"]

    result = SocrataResult(dataset=name)
    offset, page = 0, 0
    while max_pages is None or page < max_pages:
        params = build_params(spec, settings["assessor_year"], limit, offset)
        rows, limit = _get_page(session, url, params, headers, timeout, limit)
        if rows:
            flat = [flatten_record(r) for r in rows]
            # Socrata omits null keys; guarantee every selected column exists.
            path = work_dir / f"part-{page:04d}.parquet"
            write_records(flat, path, expected)
            result.files.append(path)
            result.rows += len(rows)
            if progress:
                progress(result.rows)
        if len(rows) < limit:
            break
        offset += len(rows)
        page += 1

    # Complete: replace today's pull (if any) with the new one in a single move.
    if final_dir.exists():
        shutil.rmtree(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    if work_dir.exists():
        shutil.move(str(work_dir), str(final_dir))
    result.files = [final_dir / p.name for p in result.files]
    result.page_size_used = limit
    return result


def _get_page(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    limit: int,
    attempts: int = 5,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch one page. Returns (rows, page size to use from now on)."""
    last_error = ""
    for attempt in range(attempts):
        params = {**params, "$limit": limit}
        try:
            resp = session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.Timeout:
            last_error = f"timed out after {timeout}s at page size {limit:,}"
            limit = max(limit // 2, MIN_PAGE_SIZE)  # smaller pages answer faster
            time.sleep(2 ** (attempt + 1))
            continue
        except requests.ConnectionError as exc:
            last_error = f"connection error: {exc.__class__.__name__}"
            time.sleep(2 ** (attempt + 1))
            continue
        if resp.status_code == 200:
            return resp.json(), limit
        if resp.status_code in RETRYABLE_STATUS:
            last_error = f"HTTP {resp.status_code}"
            time.sleep(2 ** (attempt + 1))
            continue
        raise SocrataError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
    raise SocrataError(f"Gave up on {url} after {attempts} attempts ({last_error})")
