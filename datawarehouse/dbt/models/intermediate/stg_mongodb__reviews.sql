select
    cast(review_id as bigint) as review_id,
    cast(customer_id as bigint) as customer_id,
    cast(product_id as bigint) as product_id,
    cast(rating as integer) as rating,
    cast(reviewed_at as timestamptz) as reviewed_at,
    try_cast(nullif(json_extract_path_text(document_json, 'verification', 'purchase_confirmed', true), '') as boolean) as is_verified_purchase,
    document_json,
    _loaded_at,
    _source,
    _batch_id
from {{ source('mongodb_raw', 'mongo_reviews') }}
