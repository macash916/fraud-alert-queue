-- Reconciliation: every raw transaction reaches staging and the feature model, no more, no fewer.
with counts as (
    select
        (select count(*) from {{ source('raw', 'raw_transactions') }}) as raw_rows,
        (select count(*) from {{ ref('stg_transactions') }})          as staging_rows,
        (select count(*) from {{ ref('fct_transaction_features') }})  as feature_rows
)
select * from counts
where raw_rows <> staging_rows or raw_rows <> feature_rows
