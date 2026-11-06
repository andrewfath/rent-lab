"""RentCast listings extractor with a hard request budget.

Every HTTP attempt is logged to `<raw>/rentcast/_requests.jsonl`. Before any
request the budget is checked against that log, so the monthly cap holds
across runs, retries and crashes. A query page already saved within
`reuse_within_days` is skipped, so re-running a command never re-spends quota.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import requests

from rentlab import config
from rentlab.storage import flatten_record, partition_dir, write_records

Kind = Literal["rental", "sale"]
Status = Literal["Active", "Inactive"]

FREE_PLAN_MONTHLY_LIMIT = 50


class BudgetExceededError(RuntimeError):
    pass


class MissingApiKeyError(RuntimeError):
    pass


@dataclass
class RequestLog:
    """Append-only log of every RentCast HTTP attempt."""

    path: Path

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def used_this_month(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        month = now.strftime("%Y-%m")
        return sum(1 for e in self.entries() if e["requested_at"].startswith(month))

    def find_saved(self, signature: str, offset: int, within_days: int) -> dict[str, Any] | None:
        cutoff = datetime.now(UTC) - timedelta(days=within_days)
        for e in reversed(self.entries()):
            if (
                e.get("signature") == signature
                and e.get("offset") == offset
                and e.get("ok")
                and datetime.fromisoformat(e["requested_at"]) >= cutoff
            ):
                return e
        return None

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


@dataclass
class PullResult:
    requests_made: int = 0
    pages_skipped: int = 0
    records_saved: int = 0
    total_available: int | None = None
    files: list[Path] = field(default_factory=list)
    stopped_reason: str = ""


def query_signature(endpoint: str, params: dict[str, Any]) -> str:
    stable = {k: v for k, v in sorted(params.items()) if k not in {"offset", "includeTotalCount"}}
    raw = endpoint + "?" + json.dumps(stable, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class RentCastClient:
    def __init__(
        self,
        api_key: str | None = None,
        raw_dir: Path | None = None,
        session: requests.Session | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings or config.sources_config()["rentcast"]
        self.api_key = api_key if api_key is not None else os.environ.get("RENTCAST_API_KEY", "")
        self.raw_dir = raw_dir or config.RAW_DIR
        self.session = session or requests.Session()
        self.log = RequestLog(self.raw_dir / "rentcast" / "_requests.jsonl")
        budget = int(self.settings["monthly_request_budget"])
        if budget > FREE_PLAN_MONTHLY_LIMIT:
            raise ValueError(
                f"monthly_request_budget={budget} exceeds the free plan's "
                f"{FREE_PLAN_MONTHLY_LIMIT}. Lower it in config/sources.yml."
            )
        self.monthly_budget = budget

    # ---- budget -----------------------------------------------------------
    def remaining_budget(self) -> int:
        return max(self.monthly_budget - self.log.used_this_month(), 0)

    def _check_budget(self) -> None:
        if self.remaining_budget() <= 0:
            raise BudgetExceededError(
                f"Monthly RentCast budget of {self.monthly_budget} requests is used up "
                f"({self.log.path}). Raise it in config/sources.yml only if you mean to."
            )

    # ---- http -------------------------------------------------------------
    def _get(self, endpoint: str, params: dict[str, Any], signature: str) -> requests.Response:
        if not self.api_key:
            raise MissingApiKeyError("RENTCAST_API_KEY is not set. Add it to your .env file.")
        url = self.settings["base_url"] + endpoint
        last_error: Exception | None = None
        for attempt in range(3):
            self._check_budget()  # every attempt counts against the budget
            requested_at = datetime.now(UTC).isoformat()
            try:
                resp = self.session.get(
                    url, params=params, headers={"X-Api-Key": self.api_key}, timeout=60
                )
            except requests.RequestException as exc:
                self.log.append(
                    {
                        "requested_at": requested_at,
                        "endpoint": endpoint,
                        "signature": signature,
                        "offset": params.get("offset", 0),
                        "ok": False,
                        "status": None,
                        "error": type(exc).__name__,
                    }
                )
                last_error = exc
                time.sleep(2**attempt)
                continue
            ok = resp.status_code == 200
            self.log.append(
                {
                    "requested_at": requested_at,
                    "endpoint": endpoint,
                    "signature": signature,
                    "offset": params.get("offset", 0),
                    "ok": ok,
                    "status": resp.status_code,
                    "records": len(resp.json()) if ok else 0,
                }
            )
            if ok:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"RentCast request failed after retries: {last_error}")

    # ---- listings ---------------------------------------------------------
    def pull_listings(
        self,
        kind: Kind,
        status: Status,
        market_id: str = "chicago",
        max_requests: int | None = None,
        property_types: list[str] | None = None,
        days_old: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        today: date | None = None,
    ) -> PullResult:
        """Page through listings until exhausted, `max_requests` is hit, or the budget runs out."""
        mkt = config.market(market_id)
        entity = f"{kind}_listings"
        endpoint = self.settings["endpoints"][entity]
        page_size = int(self.settings["page_size"])
        max_requests = max_requests or int(self.settings["default_max_requests_per_run"])
        today = today or datetime.now(UTC).date()

        params: dict[str, Any] = {
            "city": mkt["city"],
            "state": mkt["state"],
            "status": status,
            "limit": page_size,
        }
        if property_types:
            params["propertyType"] = "|".join(property_types)
        if days_old:
            params["daysOld"] = days_old
        signature = query_signature(endpoint, params)
        out_dir = partition_dir(self.raw_dir, "rentcast", entity, today)

        result = PullResult()
        offset = 0
        while True:
            saved = (
                None
                if force
                else self.log.find_saved(signature, offset, int(self.settings["reuse_within_days"]))
            )
            if saved is not None:
                result.pages_skipped += 1
                if saved.get("records", 0) < page_size:
                    result.stopped_reason = "already saved through last page"
                    break
                offset += page_size
                continue
            if result.requests_made >= max_requests:
                result.stopped_reason = f"hit --max-requests={max_requests}"
                break
            if self.remaining_budget() <= 0:
                result.stopped_reason = "monthly budget used up"
                break
            if dry_run:
                result.stopped_reason = (
                    f"dry run: next request would be offset={offset}; "
                    f"{self.remaining_budget()} requests left this month"
                )
                break

            page_params = {**params, "offset": offset}
            if offset == 0:
                page_params["includeTotalCount"] = "true"
            resp = self._get(endpoint, page_params, signature)
            result.requests_made += 1
            if offset == 0 and resp.headers.get("X-Total-Count"):
                result.total_available = int(resp.headers["X-Total-Count"])

            records = resp.json()
            if records:
                flat = [
                    {
                        **flatten_record(
                            r, self.settings["json_fields"], self.settings["drop_fields"]
                        ),
                        "_market_id": market_id,
                        "_query_signature": signature,
                    }
                    for r in records
                ]
                path = out_dir / f"q={signature}_offset={offset:06d}.parquet"
                write_records(flat, path, self.settings["expected_fields"])
                result.files.append(path)
                result.records_saved += len(records)
            if len(records) < page_size:
                result.stopped_reason = "reached last page"
                break
            offset += page_size
        return result
