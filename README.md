# rent-lab

What should a Chicago apartment rent for, and is a for-sale property worth buying as a rental?

This project builds a Chicago rent-estimate model from public data and rental listings, then
uses it to screen for-sale properties as investments. It's built in phases:

| Phase | Goal | Status |
| --- | --- | --- |
| 1 | Rent model: data layer, comparables, model with intervals, map app | **In progress**: data layer and comps done |
| 2 | Deal screener: score for-sale listings on cash flow and returns | Planned |
| 3 | Model upgrades: LLM features from listing text, photo embeddings | Planned |
| 4 | Agents: weekly listing scan with deal memos; analyst agent | Planned |

## How it fits together

```
RentCast API ─┐
Cook County ──┤  rentlab extract   ┌──────────── dbt on DuckDB ─────────────┐
Chicago data ─┼────────────────────▶ staging ─▶ intermediate ─▶ marts      ├─▶ model ─▶ app
Census, ZORI ─┘   raw Parquet       │ (per source) (canonical)  (contracts) │
                  data/raw/         └────────────────────────────────────────┘
```

- **Extract** (`src/rentlab/extract/`) only lands raw Parquet under `data/raw/<source>/<entity>/pulled_at=YYYY-MM-DD/`.
- **Staging** is the only layer that knows each source's quirks. A vendor or schema change is fixed there.
- **Intermediate** builds canonical listings, listing episodes, parcels, listing-to-parcel matches and comparables.
- **Marts** hold model-ready tables. `ml_rent_training` has an enforced dbt contract.
- Model and app code read marts only.

Adding a city means new staging models plus a row in `dbt/seeds/markets.csv` and `config/markets.yml`.

### Design notes worth knowing

- **Labels.** The target is the last asking rent before a listing came down, a proxy for the leased rent.
  RentCast's `history` field holds a unit's past listing episodes, so one API record can yield several labels.
- **Comparables.** For every episode, `int_rental_comps` finds up to 10 similar listings within 0.75 mi that
  *ended before it was listed*, never including the same listing. A test (`assert_comps_have_no_leakage`)
  enforces this, because leaked comps would make the model look far better than it is.
  The same `find_rental_comps` macro will score for-sale units in Phase 2.
- **Spatial joins** use a haversine macro and a grid prefilter in plain SQL, so there are no DuckDB extensions to install.
- **Privacy.** Owner, mailing, buyer and seller names and listing agent contacts are never extracted.

## Setup (Windows, PowerShell)

1. Install [uv](https://docs.astral.sh/uv/) once:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   Close and reopen the terminal afterwards.
2. From the repo folder, install everything. uv downloads Python 3.12 into the project and installs the
   exact versions pinned in `uv.lock`, so nothing else on your machine affects it:
   ```powershell
   cd C:\Users\<you>\dev\rent-lab
   uv sync
   ```
3. Create your `.env` and add your RentCast key (never commit this file):
   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
4. Check everything works with synthetic data (no keys, no network):
   ```powershell
   uv run pytest
   uv run rentlab dbt build --target fixtures
   ```

## Getting real data

Free sources first. These make no RentCast requests:

```powershell
uv run rentlab extract free          # Cook County, City of Chicago, Census, Zillow (10-30 minutes)
```

If a dataset fails (the city's servers are sometimes slow), the rest still run and the summary
says what to retry. Re-run only what's missing with `uv run rentlab extract free --resume`.
A dataset is moved into `data/raw/` only after all of its pages arrive.

Then RentCast. The free plan allows 50 requests a month; this project caps itself at **20**
(`config/sources.yml`), logs every request in `data/raw/rentcast/_requests.jsonl`, and never re-requests
a page it already saved. Each request returns up to 500 listings.

```powershell
uv run rentlab extract rentcast-budget                         # requests used this month (no API call)
uv run rentlab extract rentcast --status Inactive --dry-run     # shows the plan, spends nothing
uv run rentlab extract rentcast --status Inactive --max-requests 1   # one request = up to 500 listings
```

The first real request also reports how many listings match, so you can decide how many more to spend.
Inactive (past) listings are the training data. Weekly pulls of active listings wait until Phase 1 is validated.

## Build the warehouse

```powershell
uv run rentlab dbt build             # builds and tests everything into data/warehouse.duckdb
uv run rentlab dbt docs generate     # then: uv run rentlab dbt docs serve
```

Explore results from Python or any DuckDB client:

```powershell
uv run python -c "import duckdb; print(duckdb.connect('data/warehouse.duckdb').sql('select * from ml_rent_training limit 5'))"
```

## Repository layout

```
config/                  markets and source settings (dataset ids, RentCast budget)
src/rentlab/
  cli.py                 `uv run rentlab ...`
  extract/               rentcast.py (budget guard), socrata.py, census.py, zillow.py
  storage.py             raw Parquet landing
  fixtures.py            synthetic data in the same raw layout, for tests and CI
  dbt_runner.py          runs dbt with the right paths on any OS
dbt/
  models/staging/        one folder per source
  models/intermediate/   listings, episodes, parcels, matching, comps, location features
  models/marts/          dim_neighborhood, fct_rental_observations, ml_rent_training
  macros/                address/unit parsing, geo, comps, staging helpers
  tests/                 leakage, match rate, address rules, generic range tests
tests/                   pytest: extractors, budget guard, full dbt build on fixtures
```

## Data sources

- [RentCast API](https://developers.rentcast.io/reference/introduction): rental and sale listings (key required)
- [Cook County Assessor open data](https://datacatalog.cookcountyil.gov/): parcels, addresses, building characteristics, sales
- [City of Chicago Data Portal](https://data.cityofchicago.org/): CTA 'L' stops, building permits, crimes
- [Census ACS 5-year](https://www.census.gov/data/developers/data-sets/acs-5year.html): tract rents and income
- [Zillow Observed Rent Index](https://www.zillow.com/research/data/): ZIP-level rent trend

Raw RentCast data stays out of this repo; check RentCast's terms before publishing listing-level data.
