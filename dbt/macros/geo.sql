{# Great-circle distance in miles. Pure SQL, no spatial extension required. #}
{% macro haversine_mi(lat1, lon1, lat2, lon2) -%}
    (7917.6 * asin(sqrt(
        pow(sin(radians(({{ lat2 }}) - ({{ lat1 }})) / 2), 2)
        + cos(radians({{ lat1 }})) * cos(radians({{ lat2 }}))
          * pow(sin(radians(({{ lon2 }}) - ({{ lon1 }})) / 2), 2)
    )))
{%- endmacro %}


{#
  Grid cells for fast "nearby" joins. Cells are at least `radius_mi` wide, so any
  two points within radius_mi sit in the same or adjacent cells (|dx|,|dy| <= 1).
  Longitude cells assume latitude <= 60 degrees (cos(60) = 0.5), which keeps them
  wide enough for any US market outside Alaska.
#}
{% macro grid_y(lat, radius_mi) -%}
    cast(floor(({{ lat }}) / ({{ radius_mi }} / 69.0)) as bigint)
{%- endmacro %}

{% macro grid_x(lon, radius_mi) -%}
    cast(floor(({{ lon }}) / ({{ radius_mi }} / (69.0 * 0.5))) as bigint)
{%- endmacro %}

{% macro grid_neighbors(a, b) -%}
    abs({{ a }}.grid_y - {{ b }}.grid_y) <= 1 and abs({{ a }}.grid_x - {{ b }}.grid_x) <= 1
{%- endmacro %}
