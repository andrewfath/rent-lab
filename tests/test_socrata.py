from datetime import date

import pyarrow.parquet as pq
import pytest
import requests
import responses

from rentlab import config
from rentlab.extract import socrata


def test_build_params_fills_assessor_year():
    spec = config.sources_config()["socrata"]["datasets"]["cook_parcel_addresses"]
    params = socrata.build_params(spec, 2025, 100, 0)
    assert "year = 2025" in params["$where"]
    assert "mail_address" not in params["$select"]  # owner/mailing fields never pulled


@responses.activate
def test_pages_and_fills_missing_columns(raw_dir, monkeypatch):
    monkeypatch.setitem(config.sources_config()["socrata"], "page_size", 2)
    url = "https://data.cityofchicago.org/resource/8pix-ypme.json"
    responses.get(
        url,
        json=[
            {
                "stop_id": "1",
                "station_name": "Damen",
                "map_id": "9",
                "location": {"latitude": "41.9", "longitude": "-87.6", "human_address": "{}"},
            },
            {"stop_id": "2", "station_name": "Damen", "map_id": "9"},  # Socrata omits nulls
        ],
    )
    responses.get(url, json=[])
    res = socrata.pull_dataset("chicago_cta_l_stops", raw_dir=raw_dir, today=date(2026, 8, 1))
    assert res.rows == 2
    table = pq.read_table(res.files[0])
    assert {"ada", "location__latitude"} <= set(table.column_names)
    assert (
        str(res.files[0])
        .replace("\\", "/")
        .endswith("chicago_portal/cta_l_stops/pulled_at=2026-08-01/part-0000.parquet")
    )


@responses.activate
def test_timeout_retries_with_smaller_pages(raw_dir, monkeypatch):
    monkeypatch.setattr("rentlab.extract.socrata.time.sleep", lambda s: None)
    monkeypatch.setitem(config.sources_config()["socrata"], "page_size", 4000)
    url = "https://data.cityofchicago.org/resource/8pix-ypme.json"
    responses.get(url, body=requests.Timeout())
    responses.get(url, json=[{"stop_id": "1", "map_id": "9"}])
    res = socrata.pull_dataset("chicago_cta_l_stops", raw_dir=raw_dir, today=date(2026, 8, 1))
    assert res.rows == 1
    assert res.page_size_used == 2000
    assert responses.calls[1].request.params["$limit"] == "2000"


@responses.activate
def test_failed_pull_leaves_previous_pull_untouched(raw_dir, monkeypatch):
    monkeypatch.setattr("rentlab.extract.socrata.time.sleep", lambda s: None)
    monkeypatch.setitem(config.sources_config()["socrata"], "page_size", 1)
    url = "https://data.cityofchicago.org/resource/8pix-ypme.json"
    day = date(2026, 8, 1)

    responses.get(url, json=[{"stop_id": "1", "map_id": "9"}])
    responses.get(url, json=[])
    good = socrata.pull_dataset("chicago_cta_l_stops", raw_dir=raw_dir, today=day)
    assert good.rows == 1

    # Second pull: first page arrives, then the server keeps failing.
    responses.reset()
    responses.get(url, json=[{"stop_id": "2", "map_id": "9"}])
    for _ in range(5):
        responses.get(url, status=503)
    with pytest.raises(socrata.SocrataError):
        socrata.pull_dataset("chicago_cta_l_stops", raw_dir=raw_dir, today=day)

    final = raw_dir / "chicago_portal" / "cta_l_stops" / "pulled_at=2026-08-01"
    files = sorted(final.glob("*.parquet"))
    assert len(files) == 1
    assert pq.read_table(files[0]).column("stop_id").to_pylist() == ["1"]
