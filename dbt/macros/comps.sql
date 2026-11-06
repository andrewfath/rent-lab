{#
  Find rental comparables for any set of subjects, as of each subject's own date.
  Returns a complete query; wrap it as `select * from ( {{ find_rental_comps(...) }} )`.

  `subjects` must be a relation or CTE name with columns:
      subject_key, market_id, lat, lon, beds, sqft, property_type_std, as_of_date,
      exclude_listing_key (a listing_key that may never be its own comp; may be null)

  Comps are completed rental episodes that:
    * ended (removed_date) BEFORE the subject's as_of_date, and started within
      `comps_lookback_days` of it -> no information from the future
    * are not the subject's own listing                      -> no self-comps
    * lie within `comps_radius_mi` and within 1 bedroom of the subject

  Each comp gets a similarity score (lower is more similar) and a rank. The same
  macro serves training (subjects = past episodes) and Phase 2 (subjects = for-sale
  units as of today), so both see comps built the same way.
#}
{% macro find_rental_comps(subjects) %}
{% set radius = var('comps_radius_mi') %}
with subj as (
    select
        s.*,
        {{ grid_y('s.lat', radius) }} as grid_y,
        {{ grid_x('s.lon', radius) }} as grid_x
    from {{ subjects }} s
    where s.lat is not null and s.as_of_date is not null
),

pool as (
    select
        e.episode_key,
        e.listing_key,
        e.rent,
        e.listed_date,
        e.removed_date,
        l.market_id,
        l.lat,
        l.lon,
        l.beds,
        l.sqft,
        l.property_type_std,
        {{ grid_y('l.lat', radius) }} as grid_y,
        {{ grid_x('l.lon', radius) }} as grid_x
    from {{ ref('int_rental_listing_events') }} e
    join {{ ref('int_rental_listings') }} l using (listing_key)
    where e.is_completed
      and e.rent between {{ var('min_rent') }} and {{ var('max_rent') }}
      and l.lat is not null
      and l.beds is not null
),

pairs as (
    select
        subj.subject_key,
        pool.episode_key                                        as comp_episode_key,
        pool.listing_key                                        as comp_listing_key,
        pool.rent                                               as comp_rent,
        pool.sqft                                               as comp_sqft,
        pool.beds                                               as comp_beds,
        pool.property_type_std                                  as comp_property_type,
        pool.listed_date                                        as comp_listed_date,
        pool.removed_date                                       as comp_removed_date,
        {{ haversine_mi('subj.lat', 'subj.lon', 'pool.lat', 'pool.lon') }} as distance_mi,
        abs(subj.beds - pool.beds)                              as beds_diff,
        case when subj.sqft > 0 and pool.sqft > 0
             then abs(ln(subj.sqft / pool.sqft)) end            as log_sqft_diff,
        subj.property_type_std is distinct from pool.property_type_std as type_differs,
        date_diff('day', pool.removed_date, subj.as_of_date)    as days_before_subject
    from subj
    join pool
        on subj.market_id = pool.market_id
       and {{ grid_neighbors('subj', 'pool') }}
       and pool.removed_date < subj.as_of_date
       and pool.listed_date >= subj.as_of_date - interval {{ var('comps_lookback_days') }} day
       and pool.listing_key is distinct from subj.exclude_listing_key
       and abs(subj.beds - pool.beds) <= 1
),

scored as (
    select
        *,
        distance_mi / {{ radius }}
          + 0.5 * beds_diff
          + 0.5 * coalesce(log_sqft_diff, 0.2)          -- unknown size: small fixed penalty
          + 0.25 * cast(type_differs as int)
          + 0.25 * days_before_subject / {{ var('comps_lookback_days') }}
                                                        as similarity_score
    from pairs
    where distance_mi <= {{ radius }}
)

select
    *,
    row_number() over (
        partition by subject_key order by similarity_score, comp_episode_key
    ) as comp_rank
from scored
qualify comp_rank <= {{ var('comps_max') }}
{% endmacro %}
