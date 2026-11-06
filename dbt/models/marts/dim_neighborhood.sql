-- Census tract context. Joined to listings through their matched parcel's tract.
select
    tract_geoid,
    acs_year,
    median_gross_rent       as tract_median_gross_rent,
    median_contract_rent    as tract_median_contract_rent,
    median_household_income as tract_median_household_income,
    renter_share            as tract_renter_share,
    occupied_units          as tract_occupied_units
from {{ ref('stg_census__acs5_tract') }}
