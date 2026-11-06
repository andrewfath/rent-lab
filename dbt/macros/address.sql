{#
  Address normalization shared by every source, so "1834 N. Damen Avenue",
  "1834 N DAMEN AVE" and "1834 North Damen Ave Apt 2" all become "1834 N DAMEN AVE".
  Add a (pattern, replacement) pair below to teach it a new variant.
#}

{% macro address_rules() %}
    {{ return([
        ('[.,]', ''),
        ('\\s+(APT|UNIT|STE|SUITE|#|FL|FLOOR|RM)\\b.*$', ''),
        ('\\s+#.*$', ''),
        ('\\s+', ' '),
        ('\\bNORTH\\b', 'N'),
        ('\\bSOUTH\\b', 'S'),
        ('\\bEAST\\b', 'E'),
        ('\\bWEST\\b', 'W'),
        ('\\bAVENUE\\b', 'AVE'),
        ('\\bSTREET\\b', 'ST'),
        ('\\bBOULEVARD\\b', 'BLVD'),
        ('\\b(PARKWAY|PKY)\\b', 'PKWY'),
        ('\\bPLACE\\b', 'PL'),
        ('\\bDRIVE\\b', 'DR'),
        ('\\bTERRACE\\b', 'TER'),
        ('\\bCOURT\\b', 'CT'),
    ]) }}
{% endmacro %}

{% macro normalize_address(col) -%}
    {%- set ns = namespace(expr="upper(trim(coalesce(" ~ col ~ ", '')))") -%}
    {%- for pattern, replacement in address_rules() -%}
        {%- set ns.expr = "regexp_replace(" ~ ns.expr ~ ", '" ~ pattern ~ "', '" ~ replacement ~ "', 'g')" -%}
    {%- endfor -%}
    nullif(trim({{ ns.expr }}), '')
{%- endmacro %}


{#
  Unit normalization: "Apt 3R", "#3-R", "Unit 3 Rear" -> "3R"; "Garden" -> "G".
#}
{% macro unit_rules() %}
    {{ return([
        ('^(APT|APARTMENT|UNIT|STE|SUITE|NO)\\b\\s*', ''),
        ('^#\\s*', ''),
        ('\\bREAR\\b', 'R'),
        ('\\b(FRONT|FRT)\\b', 'F'),
        ('\\b(GARDEN|GDN)\\b', 'G'),
        ('[^A-Z0-9]', ''),
    ]) }}
{% endmacro %}

{% macro clean_unit(col) -%}
    {%- set ns = namespace(expr="upper(trim(coalesce(" ~ col ~ ", '')))") -%}
    {%- for pattern, replacement in unit_rules() -%}
        {%- set ns.expr = "regexp_replace(" ~ ns.expr ~ ", '" ~ pattern ~ "', '" ~ replacement ~ "', 'g')" -%}
    {%- endfor -%}
    nullif({{ ns.expr }}, '')
{%- endmacro %}
