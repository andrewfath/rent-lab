"""Project paths and YAML config loading."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` (or this file) to the folder holding pyproject.toml."""
    override = os.environ.get("RENTLAB_ROOT")
    if override:
        return Path(override).resolve()
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "config").is_dir():
            return candidate
    raise FileNotFoundError("Could not find the rent-lab project root (pyproject.toml).")


ROOT = find_root()
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DBT_DIR = ROOT / "dbt"
FIXTURE_RAW_DIR = ROOT / "tests" / "fixtures" / "raw"

load_dotenv(ROOT / ".env")


@lru_cache
def load_yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def sources_config() -> dict[str, Any]:
    return load_yaml("sources.yml")


def markets_config() -> dict[str, Any]:
    return load_yaml("markets.yml")["markets"]


def market(market_id: str) -> dict[str, Any]:
    markets = markets_config()
    if market_id not in markets:
        raise KeyError(f"Unknown market '{market_id}'. Known: {sorted(markets)}")
    return markets[market_id]
