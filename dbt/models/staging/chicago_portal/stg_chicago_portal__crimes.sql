with src as {{ latest_snapshot(source('chicago_portal', 'crimes')) }}

select
    'chicago'               as market_id,
    cast(id as varchar)     as crime_id,
    {{ iso_date('date') }}  as crime_date,
    primary_type,
    {{ num('latitude') }}   as lat,
    {{ num('longitude') }}  as lon
from src
where latitude is not null
qualify row_number() over (partition by id order by crime_date desc) = 1
