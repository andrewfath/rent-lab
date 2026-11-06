-- One row per for-sale listing per pull (Phase 2 inference input).
-- Built only once sale listings have been pulled; `rentlab dbt` detects that and
-- sets RENTLAB_INCLUDE_SALES, so Phase 1 never spends RentCast requests on sales.
{{ config(enabled=env_var('RENTLAB_INCLUDE_SALES', 'false') == 'true') }}

{{ stg_rentcast_listings(source('rentcast', 'sale_listings'), 'list_price', 'sale') }}
