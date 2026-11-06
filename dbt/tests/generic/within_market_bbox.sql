{# Fails on rows whose coordinates fall outside their market's bounding box. #}
{% test within_market_bbox(model, column_name, lon_column='lon', market_column='market_id') %}
select t.*
from {{ model }} t
join {{ ref('markets') }} m on t.{{ market_column }} = m.market_id
where t.{{ column_name }} is not null
  and (t.{{ column_name }} not between m.min_lat and m.max_lat
       or t.{{ lon_column }} not between m.min_lon and m.max_lon)
{% endtest %}
