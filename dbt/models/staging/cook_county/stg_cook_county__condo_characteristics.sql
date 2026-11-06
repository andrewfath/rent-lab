-- Condo units. pin10 identifies the building; each unit has its own 14-digit PIN.
with src as {{ latest_snapshot(source('cook_county', 'condo_characteristics')) }}

select
    {{ pin14('pin') }}                      as pin,
    lpad(cast(pin10 as varchar), 10, '0')   as pin10,
    {{ int_('year') }}                      as tax_year,
    cast(class as varchar)                  as class_code,
    {{ int_('char_yrblt') }}                as year_built,
    {{ num('char_building_sf') }}           as building_sqft,
    {{ num('char_unit_sf') }}               as unit_sqft,
    {{ int_('char_bedrooms') }}             as beds,
    {{ int_('char_full_baths') }}           as full_baths,
    {{ int_('char_half_baths') }}           as half_baths,
    {{ int_('char_building_pins') }}        as building_pins,
    try_cast(bldg_is_mixed_use as boolean)  as is_mixed_use,
    try_cast(is_parking_space as boolean)   as is_parking_space,
    try_cast(is_common_area as boolean)     as is_common_area
from src
qualify row_number() over (partition by pin order by {{ int_('card') }}) = 1
