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
        coalesce(sum(amt) over w_24h, 0)    as amt_sum_24h,
        -- Card testing: small payments in the previous 24 hours
        count(*) filter (where amt < {{ var('small_txn_usd') }}) over w_24h as small_txn_count_24h
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
        lag(trans_ts) over (partition by card_token order by trans_ts, trans_num) as prev_trans_ts,
        sum(amt) over (partition by card_token order by trans_ts, trans_num
                       rows between unbounded preceding and 1 preceding) as prior_total_amt,
        min(trans_ts) over (partition by card_token)                      as first_trans_ts
    from transactions

),

-- 4. Category norm: average of all earlier payments in this category, across every card.
--    Done in two stages for speed: total each category per second, then keep a running sum over
--    those totals that stops at the previous second. Payments at the same second don't count.
--    (A single "exclude group" window gives the same answer but can't keep a running total
--    over an unbounded history, so it re-adds every earlier row for every row.)
category_per_second as (

    select category, trans_ts, sum(amt) as amt_sum, count(*) as txn_count
    from transactions
    group by category, trans_ts

),

category_running as (

    select
        category,
        trans_ts,
        sum(amt_sum)   over w as prior_amt_sum,
        sum(txn_count) over w as prior_txn_count
    from category_per_second
    window w as (partition by category order by trans_ts
                 rows between unbounded preceding and 1 preceding)

),

category_norm as (

    select
        t.trans_num,
        r.prior_amt_sum / nullif(r.prior_txn_count, 0) as category_prior_avg_amt
    from transactions t
    join category_running r using (category, trans_ts)

),

-- 5. Card's category and time-of-day habits
card_habits as (

    select
        trans_num,
        count(*) over (partition by card_token, category order by trans_ts, trans_num
                       rows between unbounded preceding and 1 preceding) as prior_txns_in_category,
        count(*) over (partition by card_token,
                                    floor(extract(hour from trans_ts) / {{ var('hour_band_hours') }})
                       order by trans_ts, trans_num
                       rows between unbounded preceding and 1 preceding) as prior_txns_in_hour_band
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

    -- Amount vs the category's normal (null for the very first payment in a category)
    round(t.amt / nullif(c.category_prior_avg_amt, 0), 3)  as amt_vs_category_avg,

    -- First use of this category by this card
    (ch.prior_txns_in_category = 0)::int                   as is_new_category,

    -- Share of this card's earlier payments in the same time-of-day band (low = unusual hour
    -- for this customer; null on the card's first transaction)
    round(ch.prior_txns_in_hour_band::numeric / nullif(h.prior_txn_count, 0), 3) as hour_band_share,

    -- Card testing
    v.small_txn_count_24h,

    -- Spending spree: (previous 24h spend + this amount) / card's average daily spend so far.
    -- Days of history floored at 1 so a brand-new card isn't divided by a fraction of a day.
    round((v.amt_sum_24h + t.amt)
          / nullif(h.prior_total_amt
                   / greatest(extract(epoch from t.trans_ts - h.first_trans_ts) / 86400, 1), 0), 3)
                                                           as spend_24h_vs_daily_avg,

    -- Label: training target only, never a feature
    t.is_fraud

from transactions t
join velocity         v using (trans_num)
join history          h using (trans_num)
join merchant_history m using (trans_num)
join category_norm    c using (trans_num)
join card_habits      ch using (trans_num)
