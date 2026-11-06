with src as {{ latest_snapshot(source('chicago_portal', 'building_permits')) }}

select
    'chicago'                       as market_id,
    cast(id as varchar)             as permit_id,
    permit_type,
    {{ iso_date('issue_date') }}    as issue_date,
    {{ num('reported_cost') }}      as reported_cost,
    {{ num('latitude') }}           as lat,
    {{ num('longitude') }}          as lon
from src
where latitude is not null
qualify row_number() over (partition by id order by issue_date desc) = 1
