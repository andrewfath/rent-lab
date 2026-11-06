{# Full-snapshot sources (Assessor, City portal, Census, Zillow): keep only the newest pull. #}
{% macro latest_snapshot(relation) -%}
    (select * from {{ relation }}
     where pulled_at = (select max(pulled_at) from {{ relation }}))
{%- endmacro %}


{# Socrata sends numbers as strings; cast defensively. #}
{% macro num(col) -%} try_cast({{ col }} as double) {%- endmacro %}
{% macro int_(col) -%} try_cast(try_cast({{ col }} as double) as integer) {%- endmacro %}
{% macro iso_date(col) -%} try_cast(left(cast({{ col }} as varchar), 10) as date) {%- endmacro %}
{% macro pin14(col) -%} lpad(cast({{ col }} as varchar), 14, '0') {%- endmacro %}


{# Assessor publishes apartment counts as words ("Two", "Three"); older extracts used codes. #}
{% macro decode_apts(col) -%}
    case upper(trim(cast({{ col }} as varchar)))
        when 'TWO' then 2 when 'THREE' then 3 when 'FOUR' then 4
        when 'FIVE' then 5 when 'SIX' then 6 when 'NONE' then 0
        else try_cast({{ col }} as integer)
    end
{%- endmacro %}


{#
  Shared column mapping for every RentCast listings endpoint, so rental and sale
  staging models can't drift apart. `price_alias` is rent or list_price;
  `listing_kind` keeps rental and sale keys apart (RentCast reuses address ids).
#}
{% macro stg_rentcast_listings(source_relation, price_alias, listing_kind) %}
with src as (
    select * from {{ source_relation }}
),

markets as (select * from {{ ref('markets') }}),

types as (
    select source_value, property_type_std
    from {{ ref('property_type_map') }}
    where source_name = 'rentcast'
),

renamed as (
    select
        'rentcast'                                   as source_name,
        'rentcast:{{ listing_kind }}:' || src.id     as listing_key,
        src.id                                       as source_listing_id,
        coalesce(src._market_id, m.market_id)        as market_id,
        src.formattedAddress                         as formatted_address,
        src.addressLine1                             as address_line1,
        nullif(trim(src.addressLine2), '')           as address_line2,
        {{ normalize_address('src.addressLine1') }}  as address_norm,
        {{ clean_unit('src.addressLine2') }}         as unit_norm,
        lpad(cast(src.zipCode as varchar), 5, '0')   as zip_code,
        {{ num('src.latitude') }}                    as lat,
        {{ num('src.longitude') }}                   as lon,
        src.propertyType                             as property_type_source,
        t.property_type_std,
        {{ num('src.bedrooms') }}                    as beds,
        {{ num('src.bathrooms') }}                   as baths,
        {{ num('src.squareFootage') }}               as sqft,
        {{ num('src.lotSize') }}                     as lot_sqft,
        {{ int_('src.yearBuilt') }}                  as year_built,
        {{ num('src.hoa__fee') }}                    as hoa_fee,
        src.status                                   as listing_status,
        {{ num('src.price') }}                       as {{ price_alias }},
        src.listingType                              as listing_type,
        {{ iso_date('src.listedDate') }}             as listed_date,
        {{ iso_date('src.removedDate') }}            as removed_date,
        {{ iso_date('src.lastSeenDate') }}           as last_seen_date,
        {{ int_('src.daysOnMarket') }}               as days_on_market,
        src.mlsNumber                                as mls_number,
        src.history                                  as history_json,
        cast(src.pulled_at as date)                  as pulled_at
    from src
    left join markets m on src.city = m.city and src.state = m.state
    left join types t on src.propertyType = t.source_value
)

select *
from renamed
-- A listing can appear twice in one pull if two queries overlap; keep one.
qualify row_number() over (
    partition by listing_key, pulled_at order by last_seen_date desc nulls last
) = 1
{% endmacro %}
