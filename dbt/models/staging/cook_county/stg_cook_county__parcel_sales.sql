-- Recorded sales. Buyer and seller names are never extracted.
with src as {{ latest_snapshot(source('cook_county', 'parcel_sales')) }}

select
    {{ pin14('pin') }}                                  as pin,
    doc_no                                              as document_number,
    {{ iso_date('sale_date') }}                         as sale_date,
    {{ num('sale_price') }}                             as sale_price,
    cast(class as varchar)                              as class_code,
    cast(nbhd as varchar)                               as assessor_nbhd_code,
    deed_type,
    coalesce(try_cast(is_multisale as boolean), false)  as is_multi_parcel_sale,
    {{ int_('num_parcels_sale') }}                      as num_parcels_in_sale,
    -- The Assessor's own flags for sales that aren't arm's-length market sales
    coalesce(try_cast(sale_filter_same_sale_within_365 as boolean), false)
        or coalesce(try_cast(sale_filter_less_than_10k as boolean), false)
        or coalesce(try_cast(sale_filter_deed_type as boolean), false)
                                                        as is_flagged_non_market
from src
qualify row_number() over (partition by pin, doc_no order by sale_date desc) = 1
