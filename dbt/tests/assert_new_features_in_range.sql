-- Range checks for the lever B features. Any row returned is a broken feature.
select trans_num, amt_vs_category_avg, hour_band_share, small_txn_count_24h, spend_24h_vs_daily_avg
from {{ ref('fct_transaction_features') }}
where hour_band_share not between 0 and 1          -- a share must be 0-100%
   or amt_vs_category_avg <= 0                      -- amounts are positive
   or spend_24h_vs_daily_avg <= 0
   or small_txn_count_24h > txn_count_24h           -- small payments are a subset of all payments
   or (prior_txn_count = 0 and (hour_band_share is not null or spend_24h_vs_daily_avg is not null
                                or is_new_category <> 1))   -- first payment: no history, new category
