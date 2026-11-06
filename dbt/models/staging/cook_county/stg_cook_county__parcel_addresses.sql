-- Property (situs) address per PIN. Owner and mailing fields are never extracted.
with src as {{ latest_snapshot(source('cook_county', 'parcel_addresses')) }}

select
    {{ pin14('pin') }}                                  as pin,
    lpad(cast(pin10 as varchar), 10, '0')               as pin10,
    prop_address_full                                   as address_full,
    {{ normalize_address('prop_address_full') }}        as address_norm,
    lpad(cast(prop_address_zipcode_1 as varchar), 5, '0') as zip_code
from src
where prop_address_full is not null
qualify row_number() over (partition by pin order by {{ int_('year') }} desc) = 1
