-- One row per completed rental episode that passes the label rules. The label is
-- the last asking rent before the listing came down: our proxy for the leased rent.
with events as (
    select * from {{ ref('int_rental_listing_events') }}
),

listings as (
    select * from {{ ref('int_rental_listings') }}
),

matches as (
    select * from {{ ref('int_listing_to_parcel') }} where listing_kind = 'rental'
)

select
    e.episode_key,
    e.listing_key,
    l.market_id,
    l.address_norm,
    l.unit_norm,
    l.zip_code,
    l.lat,
    l.lon,
    l.property_type_std,
    l.beds,
    l.baths,
    l.sqft,
    l.year_built                as listing_year_built,
    l.hoa_fee,
    e.listed_date,
    e.removed_date,
    e.days_listed,
    e.rent,
    e.event_source,
    m.parcel_key,
    m.building_key,
    m.match_method,
    m.match_confidence
from events e
join listings l using (listing_key)
left join matches m using (listing_key)
where e.is_completed
  and e.days_listed between 1 and {{ var('max_days_on_market') }}
  and e.rent between {{ var('min_rent') }} and {{ var('max_rent') }}
  and l.property_type_std is not null
  and l.beds is not null
  and l.lat is not null
