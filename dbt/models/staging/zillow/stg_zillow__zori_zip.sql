-- Zillow Observed Rent Index by ZIP and month (month = first day of the month).
with src as {{ latest_snapshot(source('zillow', 'zori_zip')) }}

select
    lpad(cast(zip_code as varchar), 5, '0')                 as zip_code,
    date_trunc('month', {{ iso_date('month') }})::date     as month,
    {{ num('zori') }}                                       as zori
from src
where zori is not null
