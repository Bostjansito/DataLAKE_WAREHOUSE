-- Match individual business keys and source batches, not merely aggregate row counts.
{% set entities = [
    ('mysql__customers', 'customer_id'),
    ('mysql__products', 'product_id'),
    ('mysql__orders', 'order_id'),
    ('mysql__order_items', 'order_item_id'),
    ('mongodb__reviews', 'review_id'),
    ('mongodb__navigation_events', 'event_id')
] %}
{% for entity, key in entities %}
select '{{ entity }}' as entity, qa.{{ key }} as business_key, qa._batch_id,
    'invalid_quality_partition' as failure
from {{ ref('int_' ~ entity ~ '__qa') }} as qa
left join {{ ref('int_' ~ entity ~ '__valid') }} as valid
    on valid.{{ key }} = qa.{{ key }} and valid._batch_id = qa._batch_id
left join {{ ref('quarantine_' ~ entity) }} as rejected
    on (rejected.{{ key }} = qa.{{ key }}
        or (rejected.{{ key }} is null and qa.{{ key }} is null))
    and rejected._batch_id = qa._batch_id
where (qa.rejection_reason is null and valid.{{ key }} is null)
    or (qa.rejection_reason is not null and (
        rejected._batch_id is null
        or {{ values_differ('qa.rejection_reason', 'rejected.rejection_reason') }}
        or {{ values_differ('qa._source', 'rejected._source') }}
        or {{ values_differ('qa._loaded_at', 'rejected._loaded_at') }}
        or valid.{{ key }} is not null
    ))
{% if not loop.last %}union all{% endif %}
{% endfor %}
