-- ACS 5-year tract estimates. The Census API uses large negative numbers for "no data".
with src as {{ latest_snapshot(source('census', 'acs5_tract')) }},

typed as (
    select
        state || county || tract                as tract_geoid,
        {{ int_('acs_year') }}                  as acs_year,
        {{ num('B25064_001E') }}                as median_gross_rent,
        {{ num('B25058_001E') }}                as median_contract_rent,
        {{ num('B19013_001E') }}                as median_household_income,
        {{ num('B25003_001E') }}                as occupied_units,
        {{ num('B25003_003E') }}                as renter_occupied_units
    from src
)

select
    tract_geoid,
    acs_year,
    case when median_gross_rent > 0 then median_gross_rent end              as median_gross_rent,
    case when median_contract_rent > 0 then median_contract_rent end        as median_contract_rent,
    case when median_household_income > 0 then median_household_income end  as median_household_income,
    occupied_units,
    renter_occupied_units,
    renter_occupied_units / nullif(occupied_units, 0)                       as renter_share
from typed
