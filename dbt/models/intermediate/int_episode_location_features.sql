-- Location features per rental episode, measured as of the listing date so the
-- model never sees later crime or construction activity.
{% set r = var('amenity_radius_mi') %}

with episodes as (
    select
        e.episode_key,
        e.listed_date,
        l.market_id,
        l.lat,
        l.lon,
        {{ grid_y('l.lat', r) }} as grid_y,
        {{ grid_x('l.lon', r) }} as grid_x
    from {{ ref('int_rental_listing_events') }} e
    join {{ ref('int_rental_listings') }} l using (listing_key)
    where l.lat is not null
),

nearest_station as (
    select
        ep.episode_key,
        min({{ haversine_mi('ep.lat', 'ep.lon', 's.lat', 's.lon') }}) as dist_to_l_station_mi
    from episodes ep
    join {{ ref('stg_chicago_portal__cta_l_stops') }} s on ep.market_id = s.market_id
    group by ep.episode_key
),

crimes as (
    select *, {{ grid_y('lat', r) }} as grid_y, {{ grid_x('lon', r) }} as grid_x
    from {{ ref('stg_chicago_portal__crimes') }}
),

crime_counts as (
    select ep.episode_key, count(*) as crimes_12m
    from episodes ep
    join crimes c
        on ep.market_id = c.market_id
       and {{ grid_neighbors('ep', 'c') }}
       and c.crime_date <  ep.listed_date
       and c.crime_date >= ep.listed_date - interval 365 day
    where {{ haversine_mi('ep.lat', 'ep.lon', 'c.lat', 'c.lon') }} <= {{ r }}
    group by ep.episode_key
),

permits as (
    select *, {{ grid_y('lat', r) }} as grid_y, {{ grid_x('lon', r) }} as grid_x
    from {{ ref('stg_chicago_portal__building_permits') }}
),

permit_counts as (
    select
        ep.episode_key,
        count(*)                                                as permits_36m,
        count(*) filter (where p.permit_type ilike '%NEW CONSTRUCTION%') as new_construction_36m
    from episodes ep
    join permits p
        on ep.market_id = p.market_id
       and {{ grid_neighbors('ep', 'p') }}
       and p.issue_date <  ep.listed_date
       and p.issue_date >= ep.listed_date - interval 3 year
    where {{ haversine_mi('ep.lat', 'ep.lon', 'p.lat', 'p.lon') }} <= {{ r }}
    group by ep.episode_key
)

select
    ep.episode_key,
    ns.dist_to_l_station_mi,
    coalesce(cc.crimes_12m, 0)              as crimes_12m,
    coalesce(pc.permits_36m, 0)             as permits_36m,
    coalesce(pc.new_construction_36m, 0)    as new_construction_36m
from episodes ep
left join nearest_station ns using (episode_key)
left join crime_counts cc using (episode_key)
left join permit_counts pc using (episode_key)
