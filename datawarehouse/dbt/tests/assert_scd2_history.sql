-- A replay cannot add a second current version, duplicate boundary, overlap or gap.
{% for entity, key in [('customer', 'customer_id'), ('product', 'product_id')] %}
select '{{ entity }}' as entity, {{ key }} as business_key,
    'invalid_temporal_chain' as failure
from (
    select *,
        lead(valid_from) over (partition by {{ key }} order by valid_from) as next_valid_from,
        sum(case when is_current then 1 else 0 end) over (partition by {{ key }}) as current_versions
    from {{ ref('dim_' ~ entity) }}
) as versions
where current_versions <> 1
    or valid_from is null
    or (valid_to is not null and valid_to <= valid_from)
    or (next_valid_from is not null and
        (valid_to is null or valid_to <> next_valid_from))
    or (next_valid_from is null and valid_to is not null)
    or is_current <> (valid_to is null)
union all
select '{{ entity }}', source.{{ key }}, 'source_not_current'
from {{ ref('int_mysql__' ~ entity ~ 's__valid') }} as source
left join {{ ref('dim_' ~ entity) }} as dimension
    on dimension.{{ key }} = source.{{ key }} and dimension.is_current
where dimension.{{ key }} is null
    or {{ values_differ('dimension.updated_at', 'source.updated_at') }}
    or {{ values_differ('dimension.name', 'source.name') }}
{% if entity == 'customer' %}
    or {{ values_differ('dimension.email', 'source.email') }}
    or {{ values_differ('dimension.phone', 'source.phone') }}
    or {{ values_differ('dimension.city', 'source.city') }}
    or {{ values_differ('dimension.department', 'source.department') }}
    or {{ values_differ('dimension.registration_date', 'source.registration_date') }}
{% else %}
    or {{ values_differ('dimension.category', 'source.category') }}
    or {{ values_differ('dimension.price', 'source.price') }}
    or {{ values_differ('dimension.description', 'source.description') }}
    or {{ values_differ('dimension.is_active', 'source.is_active') }}
{% endif %}
{% if not loop.last %}union all{% endif %}
{% endfor %}
