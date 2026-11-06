-- Single- and multi-family buildings. One row per improvement ("card"); a PIN can have several.
with src as {{ latest_snapshot(source('cook_county', 'res_characteristics')) }}

select
    {{ pin14('pin') }}              as pin,
    {{ int_('card') }}              as card,
    {{ int_('year') }}              as tax_year,
    cast(class as varchar)          as class_code,
    {{ int_('char_yrblt') }}        as year_built,
    {{ num('char_bldg_sf') }}       as building_sqft,
    {{ num('char_land_sf') }}       as land_sqft,
    {{ int_('char_beds') }}         as beds,
    {{ int_('char_rooms') }}        as rooms,
    {{ int_('char_fbath') }}        as full_baths,
    {{ int_('char_hbath') }}        as half_baths,
    {{ decode_apts('char_apts') }}  as apartments,
    char_type_resd                  as residence_type,
    char_ext_wall                   as exterior_wall,
    char_bsmt                       as basement,
    char_air                        as central_air,
    char_gar1_size                  as garage_size,
    char_repair_cnd                 as repair_condition,
    char_renovation                 as renovation
from src
