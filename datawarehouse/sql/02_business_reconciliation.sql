-- Run on Redshift after the complete dbt sequence. The first two queries must return no rows.
-- Compare money AND units per business date; FULL JOIN also detects missing source/fact days.
with expected as (
    select cast(orders.order_date as date) as business_date,
        sum(items.quantity) as units, sum(items.subtotal) as revenue
    from intermediate.int_mysql__order_items__valid as items
    join intermediate.int_mysql__orders__valid as orders using (order_id)
    group by 1
), actual as (
    select dates.date as business_date,
        sum(sales.quantity) as units, sum(sales.subtotal) as revenue
    from marts.fct_sales as sales
    join marts.dim_date as dates using (date_sk)
    group by 1
)
select coalesce(expected.business_date, actual.business_date) as business_date,
    expected.units as source_units, actual.units as fact_units,
    expected.revenue as source_revenue, actual.revenue as fact_revenue
from expected full outer join actual using (business_date)
where expected.business_date is null or actual.business_date is null
    or expected.units <> actual.units or expected.revenue <> actual.revenue;

-- One open SCD2 version per business key, including after a successful batch replay.
select 'customer' as entity, customer_id as business_key,
    sum(case when is_current then 1 else 0 end) as current_versions
from marts.dim_customer group by customer_id
having sum(case when is_current then 1 else 0 end) <> 1
union all
select 'product', product_id, sum(case when is_current then 1 else 0 end)
from marts.dim_product group by product_id
having sum(case when is_current then 1 else 0 end) <> 1;

-- Evidence of individual rejected records, not a count-only success signal.
select 'mysql.customers' as entity, customer_id as business_key,
    _batch_id, _source, _loaded_at, rejection_reason
from quarantine.quarantine_mysql__customers
union all
select 'mysql.products', product_id, _batch_id, _source, _loaded_at, rejection_reason
from quarantine.quarantine_mysql__products
union all
select 'mysql.orders', order_id, _batch_id, _source, _loaded_at, rejection_reason
from quarantine.quarantine_mysql__orders
union all
select 'mysql.order_items', order_item_id, _batch_id, _source, _loaded_at, rejection_reason
from quarantine.quarantine_mysql__order_items
union all
select 'mongodb.reviews', review_id, _batch_id, _source, _loaded_at, rejection_reason
from quarantine.quarantine_mongodb__reviews
union all
select 'mongodb.navigation_events', event_id, _batch_id, _source, _loaded_at, rejection_reason
from quarantine.quarantine_mongodb__navigation_events
order by _batch_id, entity, business_key;
