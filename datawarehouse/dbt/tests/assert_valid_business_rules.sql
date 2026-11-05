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
select 'orders', order_id
from {{ ref('int_mysql__orders__valid') }} as orders
where total is null or total < 0 or order_date is null
    or sales_channel is null
    or sales_channel not in ('{{ var("valid_sales_channels") | join("', '") }}')
    or not exists (select 1 from {{ ref('int_mysql__customers__valid') }} as customers
        where customers.customer_id = orders.customer_id)
union all
select 'order_items', order_item_id
from {{ ref('int_mysql__order_items__valid') }} as items
where quantity is null or quantity <= 0 or unit_price is null
    or subtotal is null or abs(subtotal - unit_price * quantity) > 0.01
    or not exists (select 1 from {{ ref('int_mysql__orders__valid') }} as orders
        where orders.order_id = items.order_id)
    or not exists (select 1 from {{ ref('int_mysql__products__valid') }} as products
        where products.product_id = items.product_id)
union all
select 'reviews', review_id
from {{ ref('int_mongodb__reviews__valid') }} as reviews
where rating is null or rating not between 1 and 5 or reviewed_at is null
    or not exists (select 1 from {{ ref('int_mysql__customers__valid') }} as customers
        where customers.customer_id = reviews.customer_id)
    or not exists (select 1 from {{ ref('int_mysql__products__valid') }} as products
        where products.product_id = reviews.product_id)
union all
select 'navigation_events', event_id
from {{ ref('int_mongodb__navigation_events__valid') }} as events
where event_type is null
    or event_type not in ('{{ var("valid_event_types") | join("', '") }}')
    or occurred_at is null or sales_channel is null
    or sales_channel not in ('{{ var("valid_sales_channels") | join("', '") }}')
    or not exists (select 1 from {{ ref('int_mysql__products__valid') }} as products
        where products.product_id = events.product_id)
    or (customer_id is not null and not exists (
        select 1 from {{ ref('int_mysql__customers__valid') }} as customers
        where customers.customer_id = events.customer_id))
