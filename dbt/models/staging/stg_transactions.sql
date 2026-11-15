-- Staging: the only model that reads the raw table.
--
-- Two controls happen here, so every layer after this one is free of card numbers and personal data:
--   1. PCI DSS: the card number becomes a token using a keyed hash (HMAC-SHA256).
--      Without the key, the token can't be reversed or recomputed, even though card numbers
--      are only 16-19 digits long (an unkeyed hash of them could be brute-forced).
--   2. GDPR data minimisation: names, address, date of birth, gender and job are dropped.
--      The customer's home coordinates are used once, to compute distance from home, and
--      are not passed on.

with source as (

    select * from {{ source('raw', 'raw_transactions') }}

)

select
    trans_num,
    trans_ts,
    encode(hmac(cc_num, '{{ env_var("CARD_TOKEN_KEY") }}', 'sha256'), 'hex') as card_token,
    merchant,
    category,
    amt,

    -- Distance from the customer's home to the merchant, in km (haversine; 6371 km = Earth's radius)
    round((2 * 6371 * asin(sqrt(
          power(sin(radians(merch_lat - cust_lat) / 2), 2)
        + cos(radians(cust_lat)) * cos(radians(merch_lat))
        * power(sin(radians(merch_long - cust_long) / 2), 2)
    )))::numeric, 1) as distance_km,

    is_fraud,
    source_file

from source
