-- Tokenisation must keep cards distinct: one token per card number, no collisions, none lost.
with raw_cards as (
    select count(distinct cc_num) as n from {{ source('raw', 'raw_transactions') }}
),
tokens as (
    select count(distinct card_token) as n from {{ ref('stg_transactions') }}
)
select raw_cards.n as cards, tokens.n as tokens
from raw_cards, tokens
where raw_cards.n <> tokens.n
