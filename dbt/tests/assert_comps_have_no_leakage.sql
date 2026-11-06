-- Comps must never be the subject's own listing, and must have ended before the
-- subject was listed. Any row returned here is leakage into training features.
select c.subject_key, c.comp_episode_key, e.listing_key, e.listed_date, c.comp_removed_date
from {{ ref('int_rental_comps') }} c
join {{ ref('int_rental_listing_events') }} e on c.subject_key = e.episode_key
where c.comp_listing_key = e.listing_key
   or c.comp_removed_date >= e.listed_date
   or c.comp_listed_date < e.listed_date - interval {{ var('comps_lookback_days') }} day
