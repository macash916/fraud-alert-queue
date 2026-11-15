-- Sanity rules any analyst would expect: the last hour can't hold more transactions than the
-- last day, and a card can't have more recent transactions than it has history.
select trans_num, txn_count_1h, txn_count_24h, prior_txn_count
from {{ ref('fct_transaction_features') }}
where txn_count_1h > txn_count_24h
   or txn_count_24h > prior_txn_count
   or amt_sum_24h < 0
