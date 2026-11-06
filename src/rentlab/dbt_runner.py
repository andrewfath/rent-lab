"""Run dbt with the right project dir, profile and paths, from anywhere in the repo."""

from __future__ import annotations

import os
from pathlib import Path

from rentlab import config

TARGETS = {
    "dev": (config.RAW_DIR, config.DATA_DIR / "warehouse.duckdb"),
    "fixtures": (config.FIXTURE_RAW_DIR, config.DATA_DIR / "fixtures.duckdb"),
}


def dbt_env(target: str) -> dict[str, str]:
    raw_dir, db_path = TARGETS[target]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Forward slashes keep DuckDB glob patterns working on Windows.
    has_sales = any((Path(raw_dir) / "rentcast" / "sale_listings").glob("*/*.parquet"))
    return {
        "RENTLAB_RAW_DIR": Path(raw_dir).resolve().as_posix(),
        "RENTLAB_DUCKDB_PATH": Path(db_path).resolve().as_posix(),
        # Sale listings are a Phase 2 input; build their models only once pulled.
        "RENTLAB_INCLUDE_SALES": "true" if has_sales else "false",
    }


def run_dbt(args: list[str], target: str = "dev") -> bool:
    from dbt.cli.main import dbtRunner

    os.environ.update(dbt_env(target))
    full_args = [
        *args,
        "--project-dir",
        str(config.DBT_DIR),
        "--profiles-dir",
        str(config.DBT_DIR),
        "--target",
        target,
    ]
    result = dbtRunner().invoke(full_args)
    return bool(result.success)
