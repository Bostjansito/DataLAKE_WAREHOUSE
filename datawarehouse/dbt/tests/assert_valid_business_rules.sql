-- Every returned business key violates a DE-DW acceptance rule; zero prices remain valid.
select 'customers' as entity, customer_id as business_key
from {{ ref('int_mysql__customers__valid') }}
where name is null or email is null or email not like '%@%'
    or updated_at is null
union all
select 'products', product_id
from {{ ref('int_mysql__products__valid') }}
where category is null or price is null or price < 0 or updated_at is null
union all
select 'orders', orders.order_id
from {{ ref('int_mysql__orders__valid') }} as orders
left join {{ ref('int_mysql__customers__valid') }} as customers on customers.customer_id = orders.customer_id
where orders.total is null or orders.total < 0 or orders.order_date is null
    or orders.sales_channel is null
    or orders.sales_channel not in ('{{ var("valid_sales_channels") | join("', '") }}')
    or customers.customer_id is null
union all
select 'order_items', items.order_item_id
from {{ ref('int_mysql__order_items__valid') }} as items
left join {{ ref('int_mysql__orders__valid') }} as orders on orders.order_id = items.order_id
left join {{ ref('int_mysql__products__valid') }} as products on products.product_id = items.product_id
where items.quantity is null or items.quantity <= 0 or items.unit_price is null
    or items.subtotal is null or abs(items.subtotal - items.unit_price * items.quantity) > 0.01
    or orders.order_id is null or products.product_id is null
union all
select 'reviews', reviews.review_id
from {{ ref('int_mongodb__reviews__valid') }} as reviews
left join {{ ref('int_mysql__customers__valid') }} as customers on customers.customer_id = reviews.customer_id
left join {{ ref('int_mysql__products__valid') }} as products on products.product_id = reviews.product_id
where reviews.rating is null or reviews.rating not between 1 and 5 or reviews.reviewed_at is null
    or customers.customer_id is null or products.product_id is null
union all
select 'navigation_events', events.event_id
from {{ ref('int_mongodb__navigation_events__valid') }} as events
left join {{ ref('int_mysql__products__valid') }} as products on products.product_id = events.product_id
left join {{ ref('int_mysql__customers__valid') }} as customers on customers.customer_id = events.customer_id
where events.event_type is null
    or events.event_type not in ('{{ var("valid_event_types") | join("', '") }}')
    or events.occurred_at is null or events.sales_channel is null
    or events.sales_channel not in ('{{ var("valid_sales_channels") | join("', '") }}')
    or products.product_id is null
    or (events.customer_id is not null and customers.customer_id is null)
