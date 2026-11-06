-- Every Chicago parcel (PIN) with location and Assessor neighborhood. Cook County-specific:
-- another market would add its own stg_<county>__parcels model with the same output columns.
with src as {{ latest_snapshot(source('cook_county', 'parcel_universe')) }}

select
    'chicago'                                   as market_id,
    'chicago:' || {{ pin14('pin') }}            as parcel_key,
    {{ pin14('pin') }}                          as pin,
    lpad(cast(pin10 as varchar), 10, '0')       as pin10,
    {{ int_('year') }}                          as tax_year,
    cast(class as varchar)                      as class_code,
    cast(township_code as varchar)              as township_code,
    cast(nbhd_code as varchar)                  as assessor_nbhd_code,
    lpad(cast(zip_code as varchar), 5, '0')     as zip_code,
    {{ num('lat') }}                            as lat,
    {{ num('lon') }}                            as lon,
    cast(census_tract_geoid as varchar)         as tract_geoid
from src
qualify row_number() over (partition by pin order by tax_year desc) = 1
