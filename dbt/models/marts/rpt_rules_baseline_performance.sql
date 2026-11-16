-- Rules baseline performance by period and route.
-- Raw outcomes only: step-up pass rates and costs are applied in the cost model, not here.
--   per_day         volume a team would see each day
--   precision_pct   share of routed payments that were fraud ("hit rate")
--   recall_pct      share of all fraud in the period that this route caught
--   value_caught    share of all fraud dollars in the period that this route caught

with rules as (

    select
        case source_file when 'fraudTrain.csv' then 'train' else 'test' end as period,
        rules_route,
        amt,
        is_fraud,
        trans_ts
    from {{ ref('fct_rules_baseline') }}

),

period_totals as (

    select
        period,
        (max(trans_ts)::date - min(trans_ts)::date + 1) as days,
        count(*)                                          as txns,
        sum(is_fraud)                                     as frauds,
        sum(amt * is_fraud)                               as fraud_value
    from rules
    group by period

)

select
    r.period,
    r.rules_route,
    count(*)                                                          as payments,
    round(count(*)::numeric / max(p.days), 1)                         as per_day,
    sum(r.is_fraud)                                                   as frauds,
    round(100.0 * sum(r.is_fraud) / count(*), 1)                      as precision_pct,
    round(100.0 * sum(r.is_fraud) / max(p.frauds), 1)                 as recall_pct,
    round(sum(r.amt * r.is_fraud), 0)                                 as fraud_value_usd,
    round(100.0 * sum(r.amt * r.is_fraud) / max(p.fraud_value), 1)   as value_caught_pct
from rules r
join period_totals p using (period)
group by r.period, r.rules_route
