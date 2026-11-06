"""ACS 5-year tract-level estimates for the market's county.

The Census API reports some problems as web pages rather than errors: a rejected
key redirects to an "Invalid Key" HTML page. This module detects those cases,
retries without the key (the API allows light use without one), falls back to
the previous ACS year if the configured one isn't published, and otherwise
fails with a message that shows what the API actually sent.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from rentlab import config
from rentlab.storage import partition_dir, write_records


class CensusError(RuntimeError):
    pass


def _fetch(session: requests.Session, url: str, params: dict) -> list[list[str]]:
    resp = session.get(url, params=params, timeout=120)
    if "invalid_key" in resp.url.lower():
        raise CensusError("invalid key")
    if resp.status_code == 404:
        raise CensusError("not found")
    if resp.status_code != 200:
        raise CensusError(f"HTTP {resp.status_code}: {resp.text[:200].strip()}")
    try:
        return resp.json()
    except ValueError as exc:
        snippet = " ".join(resp.text[:200].split()) or "(empty response)"
        raise CensusError(f"response was not data: {snippet}") from exc


def pull_acs_tracts(
    raw_dir: Path | None = None,
    session: requests.Session | None = None,
    today: date | None = None,
    log=print,
) -> Path:
    settings = config.sources_config()["census"]
    raw_dir = raw_dir or config.RAW_DIR
    session = session or requests.Session()
    today = today or datetime.now(UTC).date()

    variables = list(settings["variables"])
    base_params = {
        "get": ",".join(["NAME", *variables]),
        "for": "tract:*",
        "in": f"state:{settings['state_fips']} county:{settings['county_fips']}",
    }
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    configured_year = int(settings["acs_year"])

    rows = None
    errors = []
    for year in (configured_year, configured_year - 1):
        url = f"{settings['base_url']}/{year}/acs/acs5"
        for use_key in [True, False] if key else [False]:
            params = base_params | ({"key": key} if use_key else {})
            try:
                rows = _fetch(session, url, params)
                break
            except CensusError as exc:
                errors.append(f"{year} {'with' if use_key else 'without'} key: {exc}")
                if use_key and str(exc) == "invalid key":
                    log(
                        "  Census rejected CENSUS_API_KEY (new keys must be activated from "
                        "the Census email). Retrying without a key."
                    )
        if rows is not None:
            if year != configured_year:
                log(f"  ACS {configured_year} not available; used {year}.")
            break
    if rows is None:
        raise CensusError("Census API request failed. Attempts: " + "; ".join(errors))

    header, *data = rows
    records = [dict(zip(header, row, strict=True)) | {"acs_year": year} for row in data]
    path = partition_dir(raw_dir, "census", "acs5_tract", today) / "part-0000.parquet"
    return write_records(records, path)
