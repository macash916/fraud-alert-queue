-- Leakage guard: a card's first transaction has nothing before it, so its history features
-- must be empty. If a window ever included the current or a later row, this would fail.
-- Also checks each card has exactly one first transaction.
select card_token,
       count(*) filter (where prior_txn_count = 0)                       as first_txns,
       count(*) filter (where prior_txn_count = 0
                          and (amt_vs_avg is not null or secs_since_last is not null
                               or txn_count_24h <> 0))                    as first_txns_with_history
from {{ ref('fct_transaction_features') }}
group by card_token
having count(*) filter (where prior_txn_count = 0) <> 1
    or count(*) filter (where prior_txn_count = 0
                          and (amt_vs_avg is not null or secs_since_last is not null
                               or txn_count_24h <> 0)) > 0
