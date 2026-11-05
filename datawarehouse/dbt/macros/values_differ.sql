{# Redshift does not implement IS DISTINCT FROM. Explicit NULL handling also covers booleans. #}
{% macro values_differ(left, right) -%}
(
    {{ left }} <> {{ right }}
    or ({{ left }} is null and {{ right }} is not null)
    or ({{ left }} is not null and {{ right }} is null)
)
{%- endmacro %}
