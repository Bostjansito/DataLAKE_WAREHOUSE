{# Filtro de cargas incrementales para la fila candidata (alias candidate). Carga las llaves nuevas, las filas cuya fecha de negocio cae en la ventana de reproceso (desde incremental_lookback_days antes de la fecha máxima ya cargada) y las filas cuyas llaves de dimensión resueltas cambiaron (tracked_columns), por ejemplo cuando una versión SCD2 nueva reemplaza a la anterior. #}
{% macro incremental_candidate_filter(key_column, business_date_column, tracked_columns=[]) %}
{% if is_incremental() %}
left join {{ this }} as existing_candidate
    on existing_candidate.{{ key_column }} = candidate.{{ key_column }}
where existing_candidate.{{ key_column }} is null
or candidate.{{ business_date_column }} >= (
    select cast(dateadd(day, -{{ var('incremental_lookback_days') }}, max(dates.date)) as date)
    from {{ this }} as existing
    inner join {{ ref('dim_date') }} as dates on dates.date_sk = existing.date_sk
)
{% if tracked_columns %}
or (
    existing_candidate.{{ key_column }} is not null
    and (
        {% for column in tracked_columns %}
        {{ values_differ('existing_candidate.' ~ column, 'candidate.' ~ column) }}{{ "" if loop.last else " or" }}
        {% endfor %}
    )
)
{% endif %}
{% endif %}
{% endmacro %}

{# Elimina de la tabla de hechos las filas cuya llave de origen ya no existe en la capa validada. #}
{% macro delete_orphaned_facts(sk_column, source_relation, source_key) %}
delete from {{ this }}
where {{ sk_column }} not in (
    select {{ dbt_utils.generate_surrogate_key(['cast(' ~ source_key ~ ' as varchar)']) }}
    from {{ source_relation }}
)
{% endmacro %}
