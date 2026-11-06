-- 'L' stations (the source has one row per platform direction; collapse to stations).
with src as {{ latest_snapshot(source('chicago_portal', 'cta_l_stops')) }}

select
    'chicago'                                   as market_id,
    cast(map_id as varchar)                     as station_id,
    any_value(station_name)                     as station_name,
    avg({{ num('location__latitude') }})        as lat,
    avg({{ num('location__longitude') }})       as lon,
    bool_or(try_cast(ada as boolean))           as is_ada
from src
group by map_id
