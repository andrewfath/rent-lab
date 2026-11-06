"""Command line entry point: `uv run rentlab --help`."""

from __future__ import annotations

from typing import Annotated

import typer

from rentlab import config

app = typer.Typer(
    help="rent-lab: extract data, build the warehouse, train models.", no_args_is_help=True
)
extract = typer.Typer(help="Pull raw data into data/raw/.", no_args_is_help=True)
app.add_typer(extract, name="extract")


@extract.command("rentcast")
def extract_rentcast(
    kind: Annotated[str, typer.Option(help="rental or sale")] = "rental",
    status: Annotated[str, typer.Option(help="Active or Inactive")] = "Inactive",
    max_requests: Annotated[int | None, typer.Option(help="Cap for this run")] = None,
    property_type: Annotated[list[str] | None, typer.Option(help="Repeatable filter")] = None,
    days_old: Annotated[
        str | None, typer.Option(help="e.g. '*:180' for listed in 180 days")
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="Show what would be requested")] = False,
    force: Annotated[bool, typer.Option(help="Re-request pages already saved")] = False,
    market: str = "chicago",
) -> None:
    """Pull RentCast listings, within the monthly request budget."""
    from rentlab.extract.rentcast import RentCastClient

    if kind not in ("rental", "sale") or status not in ("Active", "Inactive"):
        raise typer.BadParameter("kind must be rental|sale and status Active|Inactive")
    client = RentCastClient()
    typer.echo(
        f"Budget: {client.remaining_budget()} of {client.monthly_budget} requests left this month."
    )
    res = client.pull_listings(
        kind, status, market, max_requests, property_type, days_old, dry_run=dry_run, force=force
    )
    if res.total_available is not None:
        pages = -(-res.total_available // int(client.settings["page_size"]))
        typer.echo(f"Listings matching query: {res.total_available} ({pages} requests for all)")
    typer.echo(
        f"Requests made: {res.requests_made}; pages skipped (already saved): "
        f"{res.pages_skipped}; records saved: {res.records_saved}"
    )
    typer.echo(f"Stopped: {res.stopped_reason}")
    typer.echo(f"Budget left this month: {client.remaining_budget()}")


@extract.command("rentcast-budget")
def rentcast_budget() -> None:
    """Show RentCast requests used this month. Makes no API calls."""
    from rentlab.extract.rentcast import RentCastClient

    client = RentCastClient(api_key="")
    used = client.log.used_this_month()
    typer.echo(
        f"Used {used} of {client.monthly_budget} this month "
        f"({client.remaining_budget()} left). Log: {client.log.path}"
    )


def _pulled_today(source: str, entity: str) -> bool:
    from datetime import UTC, datetime

    from rentlab.storage import partition_dir

    today = datetime.now(UTC).date()
    return any(partition_dir(config.RAW_DIR, source, entity, today).glob("*.parquet"))


def _run_socrata(names: list[str] | None, max_pages: int | None, resume: bool) -> list[str]:
    """Pull each dataset; one failure doesn't stop the rest. Returns failed names."""
    from rentlab.extract import socrata

    failed = []
    for name in names or socrata.dataset_names():
        source, entity = socrata._source_entity(name)
        if resume and _pulled_today(source, entity):
            typer.echo(f"Skipping {name} (already pulled today)")
            continue
        typer.echo(f"Pulling {name} ...")
        try:
            res = socrata.pull_dataset(
                name,
                max_pages=max_pages,
                progress=lambda n: typer.echo(f"  ... {n:,} rows so far"),
            )
        except Exception as exc:  # report and keep going
            typer.secho(f"  FAILED: {exc}", fg="red")
            typer.echo("  Nothing was saved for this dataset; any earlier pull is untouched.")
            failed.append(name)
            continue
        typer.echo(f"  {res.rows:,} rows in {len(res.files)} file(s)")
    return failed


def _report(failed: list[str]) -> None:
    if failed:
        typer.secho(f"\nFailed: {', '.join(failed)}", fg="red")
        cmd = failed[0] if failed[0] in ("census", "zori") else f"socrata {failed[0]}"
        typer.echo(f"Re-run just those, e.g. `uv run rentlab extract {cmd}`,")
        typer.echo("or `uv run rentlab extract free --resume` to skip what already finished today.")
        raise typer.Exit(code=1)
    typer.secho("\nAll datasets pulled.", fg="green")


@extract.command("socrata")
def extract_socrata(
    names: Annotated[list[str] | None, typer.Argument(help="Dataset keys; default all")] = None,
    max_pages: Annotated[int | None, typer.Option(help="Limit pages (for testing)")] = None,
    resume: Annotated[bool, typer.Option(help="Skip datasets already pulled today")] = False,
) -> None:
    """Pull Cook County and City of Chicago open datasets (free, no key)."""
    _report(_run_socrata(names, max_pages, resume))


@extract.command("census")
def extract_census() -> None:
    """Pull ACS 5-year tract estimates."""
    from rentlab.extract.census import pull_acs_tracts

    typer.echo(f"Saved {pull_acs_tracts()}")


@extract.command("zori")
def extract_zori() -> None:
    """Pull the Zillow Observed Rent Index for the market's metro."""
    from rentlab.extract.zillow import pull_zori

    typer.echo(f"Saved {pull_zori()}")


@extract.command("free")
def extract_free(
    resume: Annotated[bool, typer.Option(help="Skip datasets already pulled today")] = False,
) -> None:
    """Pull every free source (Socrata, Census, Zillow). No RentCast requests."""
    failed = _run_socrata(None, None, resume)
    for name, source, entity, step in (
        ("census", "census", "acs5_tract", extract_census),
        ("zori", "zillow", "zori_zip", extract_zori),
    ):
        if resume and _pulled_today(source, entity):
            typer.echo(f"Skipping {name} (already pulled today)")
            continue
        typer.echo(f"Pulling {name} ...")
        try:
            step()
        except Exception as exc:
            typer.secho(f"  FAILED: {exc}", fg="red")
            failed.append(name)
    _report(failed)


@app.command()
def fixtures() -> None:
    """Generate synthetic raw data in tests/fixtures/raw (no network needed)."""
    from rentlab.fixtures import generate

    typer.echo(f"Fixtures written to {generate()}")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def dbt(
    ctx: typer.Context,
    target: Annotated[str, typer.Option(help="dev (real data) or fixtures")] = "dev",
) -> None:
    """Run any dbt command, e.g. `rentlab dbt build --target fixtures`."""
    from rentlab.dbt_runner import run_dbt

    if target == "fixtures" and not config.FIXTURE_RAW_DIR.exists():
        from rentlab.fixtures import generate

        generate()
    ok = run_dbt(list(ctx.args), target=target)
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":
    app()
