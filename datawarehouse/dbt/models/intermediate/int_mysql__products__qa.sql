select
    *,
    case
        when product_id is null then 'missing_product_id'
        when price is null then 'missing_price'
        when updated_at is null then 'missing_updated_at'
        when category is null then 'missing_category'
        when price < 0 then 'negative_price'
    end as rejection_reason
from {{ ref('stg_mysql__products') }}
