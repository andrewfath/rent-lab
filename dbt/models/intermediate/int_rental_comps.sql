-- Top comparables for every rental episode, as of the day it was listed.
-- Used for training features and for the app's comps panel.
with subjects as (
    select
        e.episode_key       as subject_key,
        l.market_id,
        l.lat,
        l.lon,
        l.beds,
        l.sqft,
        l.property_type_std,
        e.listed_date       as as_of_date,
        e.listing_key       as exclude_listing_key
    from {{ ref('int_rental_listing_events') }} e
    join {{ ref('int_rental_listings') }} l using (listing_key)
    where l.beds is not null
)

select * from (
    {{ find_rental_comps('subjects') }}
)
