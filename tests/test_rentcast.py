"""The RentCast extractor must never exceed its request budget or re-spend quota."""

from datetime import date

import pytest
import responses

from rentlab import config
from rentlab.extract.rentcast import (
    BudgetExceededError,
    MissingApiKeyError,
    RentCastClient,
)

URL = "https://api.rentcast.io/v1/listings/rental/long-term"


def settings(**overrides):
    base = dict(config.sources_config()["rentcast"])
    base.update(page_size=2, monthly_request_budget=3, default_max_requests_per_run=10)
    base.update(overrides)
    return base


def listing(i):
    return {
        "id": f"id{i}",
        "price": 2000 + i,
        "city": "Chicago",
        "state": "IL",
        "listingAgent": {"name": "secret"},
        "history": {"2024-01-01": {"price": 1}},
    }


@responses.activate
def test_paginates_until_short_page(raw_dir):
    responses.get(URL, json=[listing(1), listing(2)], headers={"X-Total-Count": "3"})
    responses.get(URL, json=[listing(3)])
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    res = client.pull_listings("rental", "Inactive", today=date(2026, 8, 1))
    assert res.requests_made == 2
    assert res.records_saved == 3
    assert res.total_available == 3
    assert res.stopped_reason == "reached last page"
    assert client.log.used_this_month() == 2
    assert responses.calls[0].request.headers["X-Api-Key"] == "k"


@responses.activate
def test_stops_at_monthly_budget(raw_dir):
    for i in range(5):
        responses.get(URL, json=[listing(2 * i), listing(2 * i + 1)])
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    res = client.pull_listings("rental", "Inactive")
    assert res.requests_made == 3  # budget is 3
    assert res.stopped_reason == "monthly budget used up"
    assert client.remaining_budget() == 0
    with pytest.raises(BudgetExceededError):
        client._check_budget()


@responses.activate
def test_respects_max_requests(raw_dir):
    for i in range(5):
        responses.get(URL, json=[listing(2 * i), listing(2 * i + 1)])
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    res = client.pull_listings("rental", "Inactive", max_requests=1)
    assert res.requests_made == 1
    assert "max-requests" in res.stopped_reason


@responses.activate
def test_rerun_skips_saved_pages(raw_dir):
    responses.get(URL, json=[listing(1)])
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    client.pull_listings("rental", "Inactive")
    again = client.pull_listings("rental", "Inactive")
    assert again.requests_made == 0
    assert again.pages_skipped == 1
    assert len(responses.calls) == 1


@responses.activate
def test_dry_run_makes_no_requests(raw_dir):
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    res = client.pull_listings("rental", "Inactive", dry_run=True)
    assert res.requests_made == 0
    assert len(responses.calls) == 0


@responses.activate
def test_failed_requests_count_against_budget(raw_dir, monkeypatch):
    monkeypatch.setattr("rentlab.extract.rentcast.time.sleep", lambda s: None)
    responses.get(URL, status=503)
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    with pytest.raises(RuntimeError, match="failed after retries"):
        client.pull_listings("rental", "Inactive")
    assert client.log.used_this_month() == 3  # all three attempts were counted
    again = client.pull_listings("rental", "Inactive", force=True)
    assert again.requests_made == 0
    assert again.stopped_reason == "monthly budget used up"
    assert len(responses.calls) == 3


def test_missing_key_fails_before_any_request(raw_dir, monkeypatch):
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)
    client = RentCastClient(api_key="", raw_dir=raw_dir, settings=settings())
    with pytest.raises(MissingApiKeyError):
        client.pull_listings("rental", "Inactive")
    assert client.log.used_this_month() == 0


def test_budget_above_free_plan_is_rejected(raw_dir):
    with pytest.raises(ValueError):
        RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings(monthly_request_budget=60))


@responses.activate
def test_contact_fields_are_dropped(raw_dir):
    import pyarrow.parquet as pq

    responses.get(URL, json=[listing(1)])
    client = RentCastClient(api_key="k", raw_dir=raw_dir, settings=settings())
    res = client.pull_listings("rental", "Inactive")
    cols = pq.read_table(res.files[0]).column_names
    assert not any(c.startswith("listingAgent") for c in cols)
    assert "history" in cols and "removedDate" in cols
