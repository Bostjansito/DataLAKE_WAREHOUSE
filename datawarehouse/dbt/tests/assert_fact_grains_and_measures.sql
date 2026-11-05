-- FULL joins detect missing facts and facts no longer valid, including dates outside the calendar.
with sales_expected as (
    select {{ dbt_utils.generate_surrogate_key(['cast(items.order_item_id as varchar)']) }} as sale_sk,
        items.quantity, items.unit_price, items.subtotal, cast(orders.order_date as date) as business_date
    from {{ ref('int_mysql__order_items__valid') }} as items
    inner join {{ ref('int_mysql__orders__valid') }} as orders using (order_id)
),
reviews_expected as (
    select {{ dbt_utils.generate_surrogate_key(['cast(review_id as varchar)']) }} as review_sk,
        rating, is_verified_purchase,
        cast(convert_timezone('UTC', '{{ var("business_timezone") }}', cast(reviewed_at as timestamp)) as date) as business_date
    from {{ ref('int_mongodb__reviews__valid') }}
),
events_expected as (
    select {{ dbt_utils.generate_surrogate_key(['cast(event_id as varchar)']) }} as navigation_event_sk,
        cast(convert_timezone('UTC', '{{ var("business_timezone") }}', cast(occurred_at as timestamp)) as date) as business_date
    from {{ ref('int_mongodb__navigation_events__valid') }}
)
select 'sales' as entity, coalesce(expected.sale_sk, facts.sale_sk) as fact_key
from sales_expected as expected
full outer join {{ ref('fct_sales') }} as facts using (sale_sk)
left join {{ ref('dim_date') }} as dates on dates.date_sk = facts.date_sk
where expected.sale_sk is null or facts.sale_sk is null
    or {{ values_differ('expected.quantity', 'facts.quantity') }}
    or {{ values_differ('expected.unit_price', 'facts.unit_price') }}
    or {{ values_differ('expected.subtotal', 'facts.subtotal') }}
    or {{ values_differ('expected.business_date', 'dates.date') }}
union all
select 'reviews', coalesce(expected.review_sk, facts.review_sk)
from reviews_expected as expected
full outer join {{ ref('fct_reviews') }} as facts using (review_sk)
left join {{ ref('dim_date') }} as dates on dates.date_sk = facts.date_sk
where expected.review_sk is null or facts.review_sk is null
    or {{ values_differ('expected.rating', 'facts.rating') }}
    or {{ values_differ('expected.is_verified_purchase', 'facts.is_verified_purchase') }}
    or {{ values_differ('expected.business_date', 'dates.date') }}
union all
select 'navigation_events', coalesce(expected.navigation_event_sk, facts.navigation_event_sk)
from events_expected as expected
full outer join {{ ref('fct_navigation_events') }} as facts using (navigation_event_sk)
left join {{ ref('dim_date') }} as dates on dates.date_sk = facts.date_sk
where expected.navigation_event_sk is null or facts.navigation_event_sk is null
    or {{ values_differ('expected.business_date', 'dates.date') }}
