-- Canonical rental listings: latest attributes per listing, plus what the weekly
-- snapshots tell us (how often seen, price range seen). New listing vendors are
-- unioned in here with the same columns.
with snapshots as (
    select * from {{ ref('stg_rentcast__rental_listings') }}
    -- A second listing vendor: union all its stg_<vendor>__rental_listings model here.
),

snapshot_stats as (
    select
        listing_key,
        min(pulled_at)          as first_pulled_at,
        max(pulled_at)          as last_pulled_at,
        count(*)                as n_snapshots,
        min(rent)               as min_rent_seen,
        max(rent)               as max_rent_seen
    from snapshots
    group by listing_key
),

latest as (
    select *
    from snapshots
    qualify row_number() over (partition by listing_key order by pulled_at desc) = 1
)

select
    latest.* exclude (pulled_at),
    snapshot_stats.* exclude (listing_key)
from latest
join snapshot_stats using (listing_key)
