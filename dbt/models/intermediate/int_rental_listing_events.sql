-- One row per listing *episode*: each time a unit came on the market.
-- RentCast's `history` holds past episodes for the same unit, so one API record
-- can yield several labeled rents. The listing's own top-level fields describe
-- its latest episode and win over the history copy of that episode.
with listings as (
    select * from {{ ref('int_rental_listings') }}
),

history_keys as (
    select listing_key, history_json, unnest(json_keys(history_json)) as history_key
    from listings
    where history_json is not null and history_json not in ('{}', 'null')
),

history_events as (
    select
        listing_key,
        json_extract_string(history_json, '$."' || history_key || '".event')   as event_type,
        {{ num("json_extract_string(history_json, '$.\"' || history_key || '\".price')") }}
                                                                                as rent,
        {{ iso_date("json_extract_string(history_json, '$.\"' || history_key || '\".listedDate')") }}
                                                                                as listed_date,
        {{ iso_date("json_extract_string(history_json, '$.\"' || history_key || '\".removedDate')") }}
                                                                                as removed_date,
        'history'                                                               as event_source,
        2                                                                       as source_priority
    from history_keys
),

current_events as (
    select
        listing_key,
        'Rental Listing'    as event_type,
        rent,
        listed_date,
        removed_date,
        'listing'           as event_source,
        1                   as source_priority
    from listings
    where listed_date is not null
),

all_events as (
    select * from current_events
    union all
    select * from history_events where event_type = 'Rental Listing' and listed_date is not null
),

deduped as (
    select *
    from all_events
    qualify row_number() over (
        partition by listing_key, listed_date order by source_priority
    ) = 1
),

-- Price changes seen across our own weekly snapshots, per episode
snapshot_prices as (
    select
        listing_key,
        listed_date,
        arg_min(rent, pulled_at)    as first_seen_rent,
        count(distinct rent)        as n_prices_seen
    from {{ ref('stg_rentcast__rental_listings') }}
    group by listing_key, listed_date
)

select
    deduped.listing_key || ':' || strftime(deduped.listed_date, '%Y-%m-%d') as episode_key,
    deduped.listing_key,
    deduped.listed_date,
    deduped.removed_date,
    deduped.rent,
    deduped.removed_date is not null                    as is_completed,
    date_diff('day', deduped.listed_date, deduped.removed_date) as days_listed,
    sp.first_seen_rent,
    coalesce(sp.n_prices_seen, 1) - 1                   as n_price_changes_seen,
    deduped.event_source
from deduped
left join snapshot_prices sp
    on deduped.listing_key = sp.listing_key and deduped.listed_date = sp.listed_date
