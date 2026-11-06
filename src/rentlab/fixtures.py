"""Synthetic fixture data in the same raw layout and shapes the extractors produce.

Lets dbt, tests and CI run end to end with no API keys or network. The data is
fake but structured like the real sources (string-typed Socrata values,
checkbox booleans, nested RentCast `history`, dropped contact fields), and it
deliberately includes messy cases: unmatched addresses, condo units, relisted
units, price cuts across weekly snapshots.
"""

from __future__ import annotations

import math
import random
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from rentlab import config
from rentlab.storage import flatten_record, partition_dir, write_records

SEED = 42

N_S_STREETS = [  # (name in assessor style, rentcast style, longitude)
    ("N DAMEN AVE", "N Damen Ave", -87.6776),
    ("N HOYNE AVE", "N Hoyne Ave", -87.6800),
    ("N LEAVITT ST", "N Leavitt St", -87.6823),
    ("N OAKLEY AVE", "N Oakley Ave", -87.6847),
    ("N WOLCOTT AVE", "N Wolcott Ave", -87.6741),
    ("N WINCHESTER AVE", "N Winchester Ave", -87.6753),
]
TRACTS = ["17031241400", "17031241500", "17031242000"]
INACTIVE_PULL = date(2026, 8, 3)
ACTIVE_PULLS = [date(2026, 8, 10), date(2026, 8, 17)]


def _lat_for_number(house_number: int) -> float:
    # Chicago grid: 800 address numbers ~ 1 mile; Madison St (0) ~ 41.8819
    return 41.8819 + house_number / 800 * (1 / 69.0)


def build_parcels(rng: random.Random) -> list[dict[str, Any]]:
    parcels = []
    pin_seq = 0
    for street_assessor, street_rc, lon in N_S_STREETS:
        for house_number in range(1500, 2500, 40):
            if rng.random() < 0.35:
                continue
            kind = rng.choices(["sf", "2flat", "3flat", "condo"], weights=[3, 4, 3, 2])[0]
            pin_seq += 1
            pin10 = f"14{pin_seq:08d}"
            lat = _lat_for_number(house_number) + rng.uniform(-0.0001, 0.0001)
            plon = lon + rng.uniform(-0.0002, 0.0002)
            units = {"sf": 1, "2flat": 2, "3flat": 3, "condo": 6}[kind]
            parcels.append(
                {
                    "pin10": pin10,
                    "kind": kind,
                    "units": units,
                    "lat": lat,
                    "lon": plon,
                    "house_number": house_number,
                    "street_assessor": street_assessor,
                    "street_rc": street_rc,
                    "zip": "60622" if house_number < 2000 else "60647",
                    "tract": TRACTS[min(int((house_number - 1500) / 350), 2)],
                    "year_built": rng.choice([1895, 1905, 1912, 1924, 1958, 2004, 2016]),
                    "bldg_sf": {"sf": 1800, "2flat": 2600, "3flat": 3600, "condo": 7200}[kind]
                    + rng.randint(-300, 300),
                }
            )
    return parcels


def assessor_tables(parcels, rng):
    universe, addresses, res_chars, condo_chars, sales = [], [], [], [], []
    for p in parcels:
        unit_pins = (
            [p["pin10"] + f"{1000 + i:04d}" for i in range(1, p["units"] + 1)]
            if p["kind"] == "condo"
            else [p["pin10"] + "0000"]
        )
        p["pins"] = unit_pins
        cls = {"sf": "205", "2flat": "211", "3flat": "211", "condo": "299"}[p["kind"]]
        for pin in unit_pins:
            universe.append(
                {
                    "pin": pin,
                    "pin10": p["pin10"],
                    "year": "2025",
                    "class": cls,
                    "township_code": "77",
                    "nbhd_code": "77011" if p["zip"] == "60622" else "71020",
                    "zip_code": p["zip"],
                    "lat": f"{p['lat']:.6f}",
                    "lon": f"{p['lon']:.6f}",
                    "census_tract_geoid": p["tract"],
                }
            )
            addresses.append(
                {
                    "pin": pin,
                    "pin10": p["pin10"],
                    "year": "2025",
                    "prop_address_full": f"{p['house_number']} {p['street_assessor']}",
                    "prop_address_city_name": "CHICAGO",
                    "prop_address_zipcode_1": p["zip"],
                }
            )
        if p["kind"] == "condo":
            for i, pin in enumerate(unit_pins):
                condo_chars.append(
                    {
                        "pin": pin,
                        "pin10": p["pin10"],
                        "year": "2025",
                        "card": "1",
                        "class": "299",
                        "township_code": "77",
                        "char_yrblt": str(p["year_built"]),
                        "char_building_sf": str(p["bldg_sf"]),
                        "char_unit_sf": str(rng.choice([750, 900, 1100, 1300])),
                        "char_bedrooms": str(rng.choice([1, 2, 2, 3])),
                        "char_full_baths": str(rng.choice([1, 2])),
                        "char_half_baths": "0",
                        "char_building_pins": str(p["units"]),
                        "bldg_is_mixed_use": False,
                        "is_parking_space": i == 5 and rng.random() < 0.5,
                        "is_common_area": False,
                    }
                )
        else:
            res_chars.append(
                {
                    "pin": unit_pins[0],
                    "year": "2025",
                    "card": "1",
                    "class": cls,
                    "township_code": "77",
                    "char_yrblt": str(p["year_built"]),
                    "char_bldg_sf": str(p["bldg_sf"]),
                    "char_land_sf": "3125",
                    "char_beds": str(3 * p["units"]),
                    "char_rooms": str(6 * p["units"]),
                    "char_fbath": str(p["units"]),
                    "char_hbath": "0",
                    # The Assessor publishes decoded words, not numeric codes
                    "char_type_resd": "2 Story" if p["kind"] != "3flat" else "3 Story +",
                    "char_apts": {"sf": "None", "2flat": "Two", "3flat": "Three"}[p["kind"]],
                    "char_ext_wall": rng.choice(["Masonry", "Frame", "Frame + Masonry"]),
                    "char_bsmt": "Full",
                    "char_air": rng.choice(["Central A/C", "No Central A/C"]),
                    "char_gar1_size": rng.choice(["None", "1 cars", "2 cars"]),
                    "char_repair_cnd": "Average",
                    "char_renovation": rng.choice(["Yes", "No"]),
                }
            )
        for pin in unit_pins:
            if rng.random() < 0.4:
                sale_date = date(2018, 1, 1) + timedelta(days=rng.randint(0, 2900))
                sales.append(
                    {
                        "pin": pin,
                        "year": str(sale_date.year),
                        "township_code": "77",
                        "nbhd": "77011",
                        "class": cls,
                        "sale_date": f"{sale_date}T00:00:00.000",
                        "sale_price": str(
                            rng.randint(3, 12)
                            * 100_000
                            * (p["units"] if p["kind"] != "condo" else 1)
                            // 2
                        ),
                        "doc_no": f"{rng.randint(10**9, 10**10 - 1)}",
                        "deed_type": "Warranty",
                        "is_multisale": False,
                        "num_parcels_sale": "1",
                        "sale_filter_same_sale_within_365": False,
                        "sale_filter_less_than_10k": False,
                        "sale_filter_deed_type": False,
                    }
                )
    return universe, addresses, res_chars, condo_chars, sales


def _rent(rng, beds, sqft, lat, kind) -> int:
    base = 1150 + 420 * beds + 0.45 * (sqft or 900)
    base *= 1 + (lat - 41.91) * 6  # north is pricier in this fake world
    base *= {"Condo": 1.08, "Multi-Family": 1.0, "Single Family": 1.15, "Apartment": 1.02}[kind]
    return int(round(base * rng.uniform(0.9, 1.1), -1))


def rentcast_listings(parcels, rng):
    """Return {pull_date: [records]} for rental listings, plus sale listing records."""
    snapshots: dict[date, list[dict]] = {
        INACTIVE_PULL: [],
        ACTIVE_PULLS[0]: [],
        ACTIVE_PULLS[1]: [],
    }
    listing_id = 0
    for p in parcels:
        unit_labels = (
            [None]
            if p["kind"] == "sf"
            else [f"Apt {i}" for i in range(1, p["units"] + 1)]
            if p["kind"] != "condo"
            else [
                rng.choice(["Unit ", "#", "Apt "]) + f"{i}{rng.choice(['', 'R', 'F'])}"
                for i in range(1, p["units"] + 1)
            ]
        )
        ptype = {
            "sf": "Single Family",
            "2flat": "Multi-Family",
            "3flat": "Multi-Family",
            "condo": "Condo",
        }[p["kind"]]
        for unit in unit_labels:
            if rng.random() < 0.3:
                continue
            listing_id += 1
            beds = rng.choice([1, 2, 2, 3]) if p["kind"] != "sf" else rng.choice([3, 4])
            sqft = rng.choice([None, 700, 850, 1000, 1200, 1500]) if p["kind"] != "sf" else 1800
            addr1 = f"{p['house_number']} {p['street_rc']}"
            mismatch = rng.random() < 0.06  # address typo -> exercises nearest-parcel fallback
            if mismatch:
                addr1 = f"{p['house_number'] + 2} {p['street_rc']}"
            base = {
                "id": f"{addr1.replace(' ', '-')}{'-' + unit.replace(' ', '') if unit else ''}"
                f",-Chicago,-IL-{p['zip']}",
                "formattedAddress": f"{addr1}{', ' + unit if unit else ''}, Chicago, IL {p['zip']}",
                "addressLine1": addr1,
                "addressLine2": unit,
                "city": "Chicago",
                "state": "IL",
                "zipCode": p["zip"],
                "county": "Cook",
                "latitude": round(p["lat"] + rng.uniform(-0.00005, 0.00005), 6),
                "longitude": round(p["lon"] + rng.uniform(-0.00005, 0.00005), 6),
                "propertyType": ptype,
                "bedrooms": beds,
                "bathrooms": 1 if beds < 3 else 2,
                "squareFootage": sqft,
                "lotSize": 3125,
                "yearBuilt": p["year_built"],
                "listingType": "Standard",
                "mlsName": "MRED",
                "mlsNumber": str(10**7 + listing_id),
                "hoa": {"fee": 300} if ptype == "Condo" else None,
                "listingAgent": {"name": "Fake Agent", "phone": "5555555555"},
                "listingOffice": {"name": "Fake Office"},
            }
            # Past episodes in `history`
            history = {}
            first = date(2023, 6, 1) + timedelta(days=rng.randint(0, 300))
            for _ in range(rng.choice([0, 1, 1, 2])):
                rent = _rent(rng, beds, sqft, p["lat"], ptype) - 100
                removed = first + timedelta(days=rng.randint(10, 75))
                history[first.isoformat()] = {
                    "event": "Rental Listing",
                    "price": rent,
                    "listingType": "Standard",
                    "listedDate": f"{first}T00:00:00.000Z",
                    "removedDate": f"{removed}T00:00:00.000Z",
                    "daysOnMarket": (removed - first).days,
                }
                first = removed + timedelta(days=rng.randint(300, 400))

            if rng.random() < 0.8:  # most listings found in the inactive (historical) pull
                listed = date(2024, 6, 1) + timedelta(days=rng.randint(0, 760))
                removed = listed + timedelta(days=rng.randint(7, 90))
                if removed >= INACTIVE_PULL:
                    removed = INACTIVE_PULL - timedelta(days=1)
                rent = _rent(rng, beds, sqft, p["lat"], ptype)
                history[listed.isoformat()] = {
                    "event": "Rental Listing",
                    "price": rent,
                    "listingType": "Standard",
                    "listedDate": f"{listed}T00:00:00.000Z",
                    "removedDate": f"{removed}T00:00:00.000Z",
                    "daysOnMarket": (removed - listed).days,
                }
                snapshots[INACTIVE_PULL].append(
                    base
                    | {
                        "status": "Inactive",
                        "price": rent,
                        "listedDate": f"{listed}T00:00:00.000Z",
                        "removedDate": f"{removed}T00:00:00.000Z",
                        "createdDate": f"{listed}T00:00:00.000Z",
                        "lastSeenDate": f"{removed}T00:00:00.000Z",
                        "daysOnMarket": (removed - listed).days,
                        "history": history,
                    }
                )
            else:  # currently active; may cut price between weekly pulls
                listed = ACTIVE_PULLS[0] - timedelta(days=rng.randint(3, 40))
                rent = _rent(rng, beds, sqft, p["lat"], ptype)
                cut = rng.random() < 0.3
                for i, pull in enumerate(ACTIVE_PULLS):
                    if i == 1 and rng.random() < 0.25:
                        continue  # leased between pulls
                    price = rent - (50 if cut and i == 1 else 0)
                    hist = history | {
                        listed.isoformat(): {
                            "event": "Rental Listing",
                            "price": price,
                            "listingType": "Standard",
                            "listedDate": f"{listed}T00:00:00.000Z",
                            "removedDate": None,
                            "daysOnMarket": (pull - listed).days,
                        }
                    }
                    snapshots[pull].append(
                        base
                        | {
                            "status": "Active",
                            "price": price,
                            "listedDate": f"{listed}T00:00:00.000Z",
                            "removedDate": None,
                            "createdDate": f"{listed}T00:00:00.000Z",
                            "lastSeenDate": f"{pull}T00:00:00.000Z",
                            "daysOnMarket": (pull - listed).days,
                            "history": hist,
                        }
                    )
    sales = []
    for p in rng.sample(parcels, k=min(15, len(parcels))):
        listed = ACTIVE_PULLS[0] - timedelta(days=rng.randint(5, 60))
        addr1 = f"{p['house_number']} {p['street_rc']}"
        ptype = {
            "sf": "Single Family",
            "2flat": "Multi-Family",
            "3flat": "Multi-Family",
            "condo": "Condo",
        }[p["kind"]]
        sales.append(
            {
                "id": f"{addr1.replace(' ', '-')},-Chicago,-IL-{p['zip']}",
                "formattedAddress": f"{addr1}, Chicago, IL {p['zip']}",
                "addressLine1": addr1,
                "addressLine2": "Unit 2" if ptype == "Condo" else None,
                "city": "Chicago",
                "state": "IL",
                "zipCode": p["zip"],
                "county": "Cook",
                "latitude": round(p["lat"], 6),
                "longitude": round(p["lon"], 6),
                "propertyType": ptype,
                "bedrooms": 3 * (p["units"] if ptype != "Condo" else 1),
                "bathrooms": p["units"],
                "squareFootage": p["bldg_sf"],
                "lotSize": 3125,
                "yearBuilt": p["year_built"],
                "status": "Active",
                "price": 150_000 * p["units"] + rng.randint(0, 200_000),
                "listingType": "Standard",
                "listedDate": f"{listed}T00:00:00.000Z",
                "removedDate": None,
                "createdDate": f"{listed}T00:00:00.000Z",
                "lastSeenDate": f"{ACTIVE_PULLS[0]}T00:00:00.000Z",
                "daysOnMarket": (ACTIVE_PULLS[0] - listed).days,
                "mlsName": "MRED",
                "mlsNumber": str(rng.randint(10**7, 10**8)),
                "hoa": None,
                "history": {},
                "listingAgent": {"name": "Fake Agent"},
            }
        )
    return snapshots, sales


def city_tables(rng):
    stations = [
        ("Damen", 41.9099, -87.6777, 40590),
        ("Western", 41.9162, -87.6874, 40130),
        ("Division", 41.9035, -87.6666, 40320),
        ("California", 41.9220, -87.6970, 40570),
    ]
    cta = []
    for i, (name, lat, lon, map_id) in enumerate(stations):
        for direction in range(2):
            cta.append(
                {
                    "stop_id": str(30000 + 2 * i + direction),
                    "station_name": name,
                    "map_id": str(map_id),
                    "ada": True,
                    "location": {
                        "latitude": str(lat),
                        "longitude": str(lon),
                        "human_address": "{}",
                    },
                }
            )
    permits = []
    for i in range(120):
        d = date(2019, 1, 1) + timedelta(days=rng.randint(0, 2700))
        permits.append(
            {
                "id": str(3_000_000 + i),
                "permit_type": rng.choice(
                    [
                        "PERMIT - RENOVATION/ALTERATION",
                        "PERMIT - NEW CONSTRUCTION",
                        "PERMIT - ELECTRIC WIRING",
                    ]
                ),
                "issue_date": f"{d}T00:00:00.000",
                "reported_cost": str(rng.randint(1, 400) * 1000),
                "latitude": f"{rng.uniform(41.900, 41.935):.6f}",
                "longitude": f"{rng.uniform(-87.690, -87.670):.6f}",
            }
        )
    crimes = []
    for i in range(600):
        d = date(2023, 1, 1) + timedelta(days=rng.randint(0, 1300))
        lat = rng.uniform(41.900, 41.935)
        # more incidents toward the south of the fake area
        if rng.random() < (41.935 - lat) * 20:
            crimes.append(
                {
                    "id": str(12_000_000 + i),
                    "date": f"{d}T12:00:00.000",
                    "primary_type": rng.choice(["THEFT", "BATTERY", "BURGLARY", "ASSAULT"]),
                    "latitude": f"{lat:.6f}",
                    "longitude": f"{rng.uniform(-87.690, -87.670):.6f}",
                }
            )
    return cta, permits, crimes


def census_rows():
    rows = []
    for i, tract in enumerate(TRACTS):
        rows.append(
            {
                "NAME": f"Census Tract {tract[-6:]}; Cook County; Illinois",
                "B25064_001E": str(1500 + 150 * i),
                "B25058_001E": str(1400 + 150 * i),
                "B19013_001E": str(90000 + 15000 * i),
                "B25003_001E": str(2000 + 100 * i),
                "B25003_003E": str(1100 + 50 * i),
                "state": "17",
                "county": "031",
                "tract": tract[-6:],
                "acs_year": 2024,
            }
        )
    return rows


def zori_rows():
    rows = []
    for zip_code, level in (("60622", 2050.0), ("60647", 1900.0)):
        for m in range(36):
            month = date(2023 + (m // 12), m % 12 + 1, 1)
            last_day = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(
                days=1
            )
            rows.append(
                {
                    "zip_code": zip_code,
                    "metro": "Chicago-Naperville-Elgin, IL-IN",
                    "month": last_day.isoformat(),
                    "zori": round(level * math.exp(0.004 * m), 2),
                }
            )
    return rows


def generate(out_dir: Path | None = None) -> Path:
    out_dir = out_dir or config.FIXTURE_RAW_DIR
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rng = random.Random(SEED)
    rc = config.sources_config()["rentcast"]
    socrata = config.sources_config()["socrata"]["datasets"]
    pull = date(2026, 8, 1)

    parcels = build_parcels(rng)
    universe, addresses, res_chars, condo_chars, sales = assessor_tables(parcels, rng)
    tables = {
        ("cook_county", "parcel_universe", "cook_parcel_universe"): universe,
        ("cook_county", "parcel_addresses", "cook_parcel_addresses"): addresses,
        ("cook_county", "res_characteristics", "cook_res_characteristics"): res_chars,
        ("cook_county", "condo_characteristics", "cook_condo_characteristics"): condo_chars,
        ("cook_county", "parcel_sales", "cook_parcel_sales"): sales,
    }
    cta, permits, crimes = city_tables(rng)
    tables |= {
        ("chicago_portal", "cta_l_stops", "chicago_cta_l_stops"): cta,
        ("chicago_portal", "building_permits", "chicago_building_permits"): permits,
        ("chicago_portal", "crimes", "chicago_crimes"): crimes,
    }
    for (source, entity, spec_name), rows in tables.items():
        expected = [c for c in socrata[spec_name]["select"] if c != "location"]
        write_records(
            [flatten_record(r) for r in rows],
            partition_dir(out_dir, source, entity, pull) / "part-0000.parquet",
            expected,
        )

    snapshots, sale_listings = rentcast_listings(parcels, rng)
    for pull_date, records in snapshots.items():
        status = "Inactive" if pull_date == INACTIVE_PULL else "Active"
        flat = [
            flatten_record(r, rc["json_fields"], rc["drop_fields"])
            | {"_market_id": "chicago", "_query_signature": f"fixture{status.lower()}"}
            for r in records
        ]
        write_records(
            flat,
            partition_dir(out_dir, "rentcast", "rental_listings", pull_date)
            / f"q=fixture{status.lower()}_offset=000000.parquet",
            rc["expected_fields"],
        )
    flat_sales = [
        flatten_record(r, rc["json_fields"], rc["drop_fields"])
        | {"_market_id": "chicago", "_query_signature": "fixturesale"}
        for r in sale_listings
    ]
    write_records(
        flat_sales,
        partition_dir(out_dir, "rentcast", "sale_listings", ACTIVE_PULLS[0])
        / "q=fixturesale_offset=000000.parquet",
        rc["expected_fields"],
    )

    write_records(
        census_rows(), partition_dir(out_dir, "census", "acs5_tract", pull) / "part-0000.parquet"
    )
    write_records(
        zori_rows(), partition_dir(out_dir, "zillow", "zori_zip", pull) / "part-0000.parquet"
    )
    return out_dir
