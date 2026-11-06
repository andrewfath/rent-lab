-- Match each listing (rental and sale) to an Assessor parcel.
-- 1. Address match: normalized street address + ZIP. Condo buildings share an
--    address across many unit PINs, so those match at building level (pin10).
-- 2. Fallback: nearest parcel centroid within max_match_distance_m.
{% set radius_mi = var('max_match_distance_m') / 1609.344 %}

with listings as (
    select listing_key, market_id, address_norm, zip_code, lat, lon, 'rental' as listing_kind
    from {{ ref('int_rental_listings') }}
    {% if env_var('RENTLAB_INCLUDE_SALES', 'false') == 'true' %}
    union all
    select listing_key, market_id, address_norm, zip_code, lat, lon, 'sale' as listing_kind
    from {{ ref('stg_rentcast__sale_listings') }}
    qualify row_number() over (partition by listing_key order by pulled_at desc) = 1
    {% endif %}
),

parcels as (
    select
        p.*,
        a.address_norm,
        {{ grid_y('p.lat', radius_mi) }} as grid_y,
        {{ grid_x('p.lon', radius_mi) }} as grid_x
    from {{ ref('int_parcels') }} p
    left join {{ ref('stg_cook_county__parcel_addresses') }} a using (pin)
    where not p.is_non_residential_unit
),

address_candidates as (
    select
        l.listing_key,
        p.parcel_key,
        p.building_key,
        p.pin10,
        {{ haversine_mi('l.lat', 'l.lon', 'p.lat', 'p.lon') }} * 1609.344 as distance_m,
        count(distinct p.pin10) over (partition by l.listing_key) as n_buildings,
        count(*) over (partition by l.listing_key)               as n_parcels
    from listings l
    join parcels p
        on l.address_norm = p.address_norm
       and l.zip_code = p.zip_code
       and l.market_id = p.market_id
),

address_matches as (
    select
        listing_key,
        parcel_key,
        building_key,
        'address'                                                  as match_method,
        case when n_parcels > 1 and n_buildings = 1 then 'building' else 'parcel' end
                                                                   as match_level,
        distance_m,
        case when n_buildings = 1 then 0.95 else 0.8 end           as match_confidence
    from address_candidates
    -- several buildings on one address: take the closest; several units in one: any unit
    qualify row_number() over (
        partition by listing_key order by distance_m nulls last, parcel_key
    ) = 1
),

unmatched as (
    select l.*,
        {{ grid_y('l.lat', radius_mi) }} as grid_y,
        {{ grid_x('l.lon', radius_mi) }} as grid_x
    from listings l
    where l.listing_key not in (select listing_key from address_matches)
      and l.lat is not null
),

nearest_matches as (
    select
        u.listing_key,
        p.parcel_key,
        p.building_key,
        'nearest'                                                  as match_method,
        case when p.building_type = 'condo' then 'building' else 'parcel' end as match_level,
        {{ haversine_mi('u.lat', 'u.lon', 'p.lat', 'p.lon') }} * 1609.344 as distance_m
    from unmatched u
    join parcels p
        on u.market_id = p.market_id
       and {{ grid_neighbors('u', 'p') }}
    where {{ haversine_mi('u.lat', 'u.lon', 'p.lat', 'p.lon') }} * 1609.344
          <= {{ var('max_match_distance_m') }}
    qualify row_number() over (partition by u.listing_key order by distance_m, p.parcel_key) = 1
)

select
    l.listing_key,
    l.listing_kind,
    m.parcel_key,
    m.building_key,
    coalesce(m.match_method, 'unmatched')   as match_method,
    m.match_level,
    round(m.distance_m, 1)                  as match_distance_m,
    coalesce(
        m.match_confidence,
        -- nearest-centroid matches lose confidence with distance
        case when m.match_method = 'nearest'
             then round(0.7 * (1 - m.distance_m / {{ var('max_match_distance_m') }}), 3) end,
        0
    )                                       as match_confidence
from listings l
left join (
    select listing_key, parcel_key, building_key, match_method, match_level, distance_m,
           match_confidence
    from address_matches
    union all
    select listing_key, parcel_key, building_key, match_method, match_level, distance_m,
           null as match_confidence
    from nearest_matches
) m using (listing_key)
