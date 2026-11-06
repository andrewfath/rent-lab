-- Canonical parcels with building attributes. Condo units carry their building's
-- totals (via pin10) so a condo listing matched at building level still gets
-- building age and size. Market-specific parcel models are unioned here.
with universe as (
    select * from {{ ref('stg_cook_county__parcel_universe') }}
),

res as (
    select
        pin,
        count(*)                    as n_buildings,
        max(year_built)             as year_built,
        sum(building_sqft)          as building_sqft,
        sum(land_sqft)              as land_sqft,
        sum(beds)                   as beds,
        sum(full_baths)             as full_baths,
        sum(apartments)             as apartments,
        any_value(exterior_wall)    as exterior_wall,
        any_value(central_air)      as central_air,
        any_value(garage_size)      as garage_size,
        any_value(repair_condition) as repair_condition
    from {{ ref('stg_cook_county__res_characteristics') }}
    group by pin
),

condo_units as (
    select * from {{ ref('stg_cook_county__condo_characteristics') }}
),

condo_buildings as (
    select
        pin10,
        count(*) filter (where not coalesce(is_parking_space, false)
                         and not coalesce(is_common_area, false))  as building_units,
        max(year_built)                                            as year_built,
        max(building_sqft)                                         as building_sqft
    from condo_units
    group by pin10
)

select
    u.market_id,
    u.parcel_key,
    u.market_id || ':' || u.pin10                       as building_key,
    u.pin,
    u.pin10,
    u.class_code,
    case
        when u.class_code = '299'                       then 'condo'
        when u.class_code in ('211', '212')             then 'small_multifamily'
        when u.class_code like '3%'                     then 'large_multifamily'
        when u.class_code in ('210', '295')             then 'townhouse'
        when u.class_code like '2%'                     then 'single_family'
        else 'other'
    end                                                 as building_type,
    u.township_code,
    u.assessor_nbhd_code,
    u.zip_code,
    u.tract_geoid,
    u.lat,
    u.lon,
    coalesce(res.year_built, cb.year_built)             as year_built,
    coalesce(res.building_sqft, cb.building_sqft)       as building_sqft,
    res.land_sqft,
    case
        when u.class_code = '299' then cb.building_units
        when res.apartments > 0 then res.apartments
        when u.class_code like '2%' then 1
    end                                                 as building_units,
    cu.unit_sqft                                        as condo_unit_sqft,
    coalesce(cu.is_parking_space or cu.is_common_area, false) as is_non_residential_unit,
    res.exterior_wall,
    res.central_air,
    res.garage_size,
    res.repair_condition
from universe u
left join res using (pin)
left join condo_units cu using (pin)
left join condo_buildings cb on u.pin10 = cb.pin10
