-- Model features: one row per transaction.
--
-- Leakage rule: every feature uses only information available BEFORE the transaction it
-- describes. Each window stops at the previous row (rows ... 1 preceding) or excludes the
-- current timestamp (exclude group). Nothing ever looks forward.

with transactions as (

    select * from {{ ref('stg_transactions') }}

),

-- 1. Spend velocity: how busy has this card been in the hour / day before this transaction?
--    Range windows work on clock time, not row counts. Exclude group drops the current row
--    and anything at the identical timestamp, so only strictly earlier transactions count.
velocity as (

    select
        trans_num,
        count(*) over w_1h                  as txn_count_1h,
        count(*) over w_24h                 as txn_count_24h,
        coalesce(sum(amt) over w_24h, 0)    as amt_sum_24h
    from transactions
    window
        w_1h  as (partition by card_token order by trans_ts
                  range between interval '1 hour'   preceding and current row exclude group),
        w_24h as (partition by card_token order by trans_ts
                  range between interval '24 hours' preceding and current row exclude group)

),

-- 2. Card history: the customer's earlier average spend and time since their last transaction.
--    trans_num breaks ties so the order is always the same.
history as (

    select
        trans_num,
        avg(amt) over (partition by card_token order by trans_ts, trans_num
                       rows between unbounded preceding and 1 preceding) as prior_avg_amt,
        count(*) over (partition by card_token order by trans_ts, trans_num
                       rows between unbounded preceding and 1 preceding) as prior_txn_count,
        lag(trans_ts) over (partition by card_token order by trans_ts, trans_num) as prev_trans_ts
    from transactions

),

-- 3. New merchant: has this card been used at this merchant before?
merchant_history as (

    select
        trans_num,
        count(*) over (partition by card_token, merchant order by trans_ts, trans_num
                       rows between unbounded preceding and 1 preceding) as prior_visits_to_merchant
    from transactions

)

select
    t.trans_num,
    t.trans_ts,
    t.card_token,
    t.merchant,
    t.source_file,

    -- Transaction context
    t.amt,
    t.category,
    extract(hour from t.trans_ts)::int                    as hour_of_day,

    -- Spend velocity
    v.txn_count_1h,
    v.txn_count_24h,
    v.amt_sum_24h,

    -- Amount vs this customer's own history (null on a card's first transaction: no history yet)
    h.prior_txn_count,
    round(h.prior_avg_amt, 2)                            as prior_avg_amt,
    round(t.amt / nullif(h.prior_avg_amt, 0), 3)         as amt_vs_avg,

    -- Distance from home (computed in staging, so home coordinates never reach this layer)
    t.distance_km,

    -- New merchant for this card
    (m.prior_visits_to_merchant = 0)::int                 as is_new_merchant,

    -- Seconds since this card's previous transaction (null on its first)
    extract(epoch from t.trans_ts - h.prev_trans_ts)::bigint as secs_since_last,

    -- Label: training target only, never a feature
    t.is_fraud

from transactions t
join velocity         v using (trans_num)
join history          h using (trans_num)
join merchant_history m using (trans_num)
