from datetime import date

import pyarrow.parquet as pq
import pytest
import responses

from rentlab.extract import census

BASE = "https://api.census.gov/data"
ROWS = [
    [
        "NAME",
        "B25064_001E",
        "B25058_001E",
        "B19013_001E",
        "B25003_001E",
        "B25003_003E",
        "state",
        "county",
        "tract",
    ],
    ["Tract 1", "1500", "1400", "90000", "2000", "1100", "17", "031", "010100"],
]


@responses.activate
def test_rejected_key_falls_back_to_no_key(raw_dir, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "not-activated")
    # A rejected key redirects to an HTML page with status 200
    responses.get(
        f"{BASE}/2024/acs/acs5",
        status=302,
        headers={"Location": f"{BASE}/invalid_key.html"},
        match=[
            responses.matchers.query_param_matcher({"key": "not-activated"}, strict_match=False)
        ],
    )
    responses.get(f"{BASE}/invalid_key.html", body="<html>Invalid Key</html>")
    responses.get(f"{BASE}/2024/acs/acs5", json=ROWS)
    messages = []
    path = census.pull_acs_tracts(raw_dir=raw_dir, today=date(2026, 11, 3), log=messages.append)
    assert pq.read_table(path).num_rows == 1
    assert any("rejected" in m for m in messages)


@responses.activate
def test_falls_back_to_previous_year(raw_dir, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    responses.get(f"{BASE}/2024/acs/acs5", status=404)
    responses.get(f"{BASE}/2023/acs/acs5", json=ROWS)
    path = census.pull_acs_tracts(raw_dir=raw_dir, today=date(2026, 11, 3), log=lambda m: None)
    assert pq.read_table(path).column("acs_year").to_pylist() == [2023]


@responses.activate
def test_non_json_response_explains_itself(raw_dir, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    responses.get(f"{BASE}/2024/acs/acs5", body="<html>Service unavailable</html>")
    responses.get(f"{BASE}/2023/acs/acs5", body="")
    with pytest.raises(census.CensusError, match="Service unavailable"):
        census.pull_acs_tracts(raw_dir=raw_dir, log=lambda m: None)
