{% set processes = [
    ('sales', 'sale_sk', 'order_item_id'),
    ('reviews', 'review_sk', 'review_id'),
    ('navigation_events', 'navigation_event_sk', 'event_id')
] %}
{% for process, fact_key, source_key in processes %}
select '{{ process }}' as process, facts.{{ fact_key }} as fact_key
from {{ ref('fct_' ~ process) }} as facts
inner join (
{% if process == 'sales' %}
    select items.order_item_id, items.product_id, orders.customer_id,
        orders.order_date as business_at, orders.sales_channel
    from {{ ref('int_mysql__order_items__valid') }} as items
    inner join {{ ref('int_mysql__orders__valid') }} as orders using (order_id)
{% else %}
    select *, convert_timezone('UTC', '{{ var("business_timezone") }}',
        cast({{ 'reviewed_at' if process == 'reviews' else 'occurred_at' }} as timestamp)) as business_at
    from {{ ref('int_mongodb__' ~ process ~ '__valid') }}
{% endif %}
) as source
    on facts.{{ fact_key }} = {{ dbt_utils.generate_surrogate_key(['cast(source.' ~ source_key ~ ' as varchar)']) }}
left join (
    select *, min(valid_from) over (partition by customer_id) as first_valid_from
    from {{ ref('dim_customer') }}
) as customer on customer.customer_sk = facts.customer_sk
left join (
    select *, min(valid_from) over (partition by product_id) as first_valid_from
    from {{ ref('dim_product') }}
) as product on product.product_sk = facts.product_sk
{% if process != 'reviews' %}
left join {{ ref('dim_sales_channel') }} as channel on channel.sales_channel_sk = facts.sales_channel_sk
{% endif %}
{% if process == 'navigation_events' %}
left join {{ ref('dim_event_type') }} as event_type on event_type.event_type_sk = facts.event_type_sk
{% endif %}
where {{ values_differ('source.customer_id', 'customer.customer_id') }}
    or {{ values_differ('source.product_id', 'product.product_id') }}
    or (source.customer_id is null and facts.customer_sk is not null)
    or (source.customer_id is not null and not (
        (source.business_at >= customer.valid_from
            and (customer.valid_to is null or source.business_at < customer.valid_to))
        or (source.business_at < customer.valid_from and customer.valid_from = customer.first_valid_from)
    ))
    or not (
        (source.business_at >= product.valid_from
            and (product.valid_to is null or source.business_at < product.valid_to))
        or (source.business_at < product.valid_from and product.valid_from = product.first_valid_from)
    )
{% if process != 'reviews' %}
    or {{ values_differ('source.sales_channel', 'channel.sales_channel') }}
{% endif %}
{% if process == 'navigation_events' %}
    or {{ values_differ('source.event_type', 'event_type.event_type') }}
{% endif %}
{% if not loop.last %}union all{% endif %}
{% endfor %}
