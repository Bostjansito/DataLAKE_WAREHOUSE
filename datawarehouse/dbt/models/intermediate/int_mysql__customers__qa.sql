select
    *,
    case
        when customer_id is null then 'missing_customer_id'
        when updated_at is null then 'missing_updated_at'
        when name is null then 'missing_name'
        when email is null or email not like '%@%' then 'invalid_email'
    end as rejection_reason
from {{ ref('stg_mysql__customers') }}
