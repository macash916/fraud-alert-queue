-- Feature views for the card-fraud alert queue.
--
-- Leakage rule: every feature uses only information available BEFORE the transaction
-- it describes. Each window below stops at the previous row (ROWS ... 1 PRECEDING) or
-- excludes the current timestamp (EXCLUDE GROUP). Nothing ever looks forward.
--
-- Personal fields (name, address, date of birth, gender) are deliberately not used.

DROP VIEW IF EXISTS v_transaction_features;

CREATE VIEW v_transaction_features AS
WITH

-- 1. Spend velocity: how busy has this card been in the hour / day before this transaction?
--    RANGE windows work on clock time, not row counts. EXCLUDE GROUP drops the current row
--    and any other transaction at the identical timestamp, so only strictly earlier ones count.
velocity AS (
    SELECT
        trans_num,
        COUNT(*) OVER w_1h          AS txn_count_1h,
        COUNT(*) OVER w_24h         AS txn_count_24h,
        COALESCE(SUM(amt) OVER w_24h, 0) AS amt_sum_24h
    FROM raw_transactions
    WINDOW
        w_1h  AS (PARTITION BY cc_num ORDER BY trans_ts
                  RANGE BETWEEN INTERVAL '1 hour'   PRECEDING AND CURRENT ROW EXCLUDE GROUP),
        w_24h AS (PARTITION BY cc_num ORDER BY trans_ts
                  RANGE BETWEEN INTERVAL '24 hours' PRECEDING AND CURRENT ROW EXCLUDE GROUP)
),

-- 2. Card history: the customer's earlier average spend, and the time since their last transaction.
--    trans_num breaks ties so the ordering is always the same.
history AS (
    SELECT
        trans_num,
        AVG(amt) OVER (PARTITION BY cc_num ORDER BY trans_ts, trans_num
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prior_avg_amt,
        COUNT(*) OVER (PARTITION BY cc_num ORDER BY trans_ts, trans_num
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prior_txn_count,
        LAG(trans_ts) OVER (PARTITION BY cc_num ORDER BY trans_ts, trans_num) AS prev_trans_ts
    FROM raw_transactions
),

-- 3. New merchant: has this card been used at this merchant before?
merchant_history AS (
    SELECT
        trans_num,
        COUNT(*) OVER (PARTITION BY cc_num, merchant ORDER BY trans_ts, trans_num
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prior_visits_to_merchant
    FROM raw_transactions
)

SELECT
    t.trans_num,
    t.trans_ts,
    t.cc_num,
    t.merchant,
    t.source_file,

    -- Transaction context
    t.amt,
    t.category,
    EXTRACT(HOUR FROM t.trans_ts)::int                    AS hour_of_day,

    -- Spend velocity
    v.txn_count_1h,
    v.txn_count_24h,
    v.amt_sum_24h,

    -- Amount vs this customer's own history (NULL on a card's first transaction: no history yet)
    h.prior_txn_count,
    ROUND(h.prior_avg_amt, 2)                            AS prior_avg_amt,
    ROUND(t.amt / NULLIF(h.prior_avg_amt, 0), 3)         AS amt_vs_avg,

    -- Distance from home in km (haversine formula; 6371 km = Earth's radius)
    ROUND((2 * 6371 * ASIN(SQRT(
          POWER(SIN(RADIANS(t.merch_lat - t.cust_lat) / 2), 2)
        + COS(RADIANS(t.cust_lat)) * COS(RADIANS(t.merch_lat))
        * POWER(SIN(RADIANS(t.merch_long - t.cust_long) / 2), 2)
    )))::numeric, 1)                                     AS distance_km,

    -- New merchant for this card
    (m.prior_visits_to_merchant = 0)::int                 AS is_new_merchant,

    -- Seconds since this card's previous transaction (NULL on its first)
    EXTRACT(EPOCH FROM t.trans_ts - h.prev_trans_ts)::bigint AS secs_since_last,

    -- Label: only used as the training target, never as a feature
    t.is_fraud

FROM raw_transactions t
JOIN velocity         v USING (trans_num)
JOIN history          h USING (trans_num)
JOIN merchant_history m USING (trans_num);
