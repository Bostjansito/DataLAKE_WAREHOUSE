select
    *,
    case
        when order_item_id is null then 'missing_order_item_id'
        when quantity is null then 'missing_quantity'
        when unit_price is null then 'missing_unit_price'
        when subtotal is null then 'missing_subtotal'
        when order_id is null or order_id not in (select order_id from {{ ref('int_mysql__orders__valid') }}) then 'orphan_order'
        when product_id is null or product_id not in (select product_id from {{ ref('int_mysql__products__valid') }}) then 'orphan_product'
        when quantity <= 0 then 'invalid_quantity'
        when abs(subtotal - unit_price * quantity) > 0.01 then 'subtotal_mismatch'
    end as rejection_reason
from {{ ref('stg_mysql__order_items') }}
