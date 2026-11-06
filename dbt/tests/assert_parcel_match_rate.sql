-- Warn if too few rental listings match a parcel; building features would be starved.
{{ config(severity='warn') }}

select listing_kind, avg(case when match_method <> 'unmatched' then 1.0 else 0 end) as match_rate
from {{ ref('int_listing_to_parcel') }}
group by listing_kind
having avg(case when match_method <> 'unmatched' then 1.0 else 0 end)
       < {{ var('min_parcel_match_rate') }}
