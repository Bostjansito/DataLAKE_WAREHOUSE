{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='quarantine_sk') }}

select
    {{ dbt_utils.generate_surrogate_key(['_batch_id', 'order_id']) }} as quarantine_sk,
    *
from {{ ref('int_mysql__orders__qa') }}
where rejection_reason is not null
