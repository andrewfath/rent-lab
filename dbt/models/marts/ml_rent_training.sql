-- The flat, model-ready table that ml/ code reads. Columns and types are locked by
-- a dbt contract (_marts__models.yml), so an upstream source change fails here,
-- loudly, instead of silently changing the model's inputs.
with obs as (
    select * from {{ ref('fct_rental_observations') }}
),

parcels as (
    select * from {{ ref('int_parcels') }}
),

zori as (
    select * from {{ ref('stg_zillow__zori_zip') }}
)

select
    -- identifiers and label
    cast(obs.episode_key as varchar)                    as episode_key,
    cast(obs.market_id as varchar)                      as market_id,
    cast(obs.listed_date as date)                       as listed_date,
    cast(obs.rent as double)                            as rent,
    cast(ln(obs.rent) as double)                        as log_rent,

    -- unit
    cast(obs.property_type_std as varchar)              as property_type,
    cast(obs.beds as double)                            as beds,
    cast(obs.baths as double)                           as baths,
    cast(coalesce(obs.sqft, p.condo_unit_sqft) as double) as sqft,
    cast(obs.hoa_fee as double)                         as hoa_fee,

    -- building (from the matched parcel)
    cast(p.building_type as varchar)                    as building_type,
    cast(coalesce(p.year_built, obs.listing_year_built) as integer) as year_built,
    cast(p.building_units as integer)                   as building_units,
    cast(p.building_sqft as double)                     as building_sqft,
    cast(p.exterior_wall as varchar)                    as exterior_wall,
    cast(p.central_air as varchar)                      as central_air,
    cast(obs.match_confidence as double)                as parcel_match_confidence,

    -- location
    cast(obs.lat as double)                             as lat,
    cast(obs.lon as double)                             as lon,
    cast(obs.zip_code as varchar)                       as zip_code,
    cast(p.assessor_nbhd_code as varchar)               as assessor_nbhd_code,
    cast(p.tract_geoid as varchar)                      as tract_geoid,
    cast(loc.dist_to_l_station_mi as double)            as dist_to_l_station_mi,
    cast(loc.crimes_12m as integer)                     as crimes_12m,
    cast(loc.permits_36m as integer)                    as permits_36m,
    cast(loc.new_construction_36m as integer)           as new_construction_36m,

    -- neighborhood
    cast(n.tract_median_gross_rent as double)           as tract_median_gross_rent,
    cast(n.tract_median_household_income as double)     as tract_median_household_income,
    cast(n.tract_renter_share as double)                as tract_renter_share,

    -- market level at listing time (ZORI for the ZIP, month before listing)
    cast(z.zori as double)                              as zip_zori,

    -- comparables (built only from listings that ended before this one started)
    cast(coalesce(c.comp_count, 0) as integer)          as comp_count,
    cast(c.comp_median_rent as double)                  as comp_median_rent,
    cast(c.comp_median_rent_per_sqft as double)         as comp_median_rent_per_sqft,
    cast(c.comp_weighted_rent as double)                as comp_weighted_rent,
    cast(c.comp_mean_distance_mi as double)             as comp_mean_distance_mi
from obs
left join parcels p on obs.parcel_key = p.parcel_key
left join {{ ref('int_episode_location_features') }} loc using (episode_key)
left join {{ ref('dim_neighborhood') }} n on p.tract_geoid = n.tract_geoid
left join zori z
    on obs.zip_code = z.zip_code
   and z.month = date_trunc('month', obs.listed_date - interval 1 month)
left join {{ ref('int_rental_comp_features') }} c using (episode_key)
