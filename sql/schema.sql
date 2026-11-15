-- Raw layer for the card-fraud alert queue.
-- Two tables:
--   staging_transactions : matches the Kaggle CSV exactly, so COPY can load it as-is.
--   raw_transactions     : the typed system of record that everything else reads from.

-- pgcrypto provides hmac(), used by dbt to turn card numbers into keyed tokens (PCI DSS).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS staging_transactions;
CREATE TABLE staging_transactions (
    row_index              BIGINT,   -- unnamed pandas index column in the CSV; not kept
    trans_date_trans_time  TEXT,
    cc_num                 TEXT,
    merchant               TEXT,
    category               TEXT,
    amt                    TEXT,
    first                  TEXT,
    last                   TEXT,
    gender                 TEXT,
    street                 TEXT,
    city                   TEXT,
    state                  TEXT,
    zip                    TEXT,
    lat                    TEXT,
    long                   TEXT,
    city_pop               TEXT,
    job                    TEXT,
    dob                    TEXT,
    trans_num              TEXT,
    unix_time              TEXT,
    merch_lat              TEXT,
    merch_long             TEXT,
    is_fraud               TEXT
);

DROP TABLE IF EXISTS raw_transactions CASCADE;
CREATE TABLE raw_transactions (
    trans_num      TEXT PRIMARY KEY,          -- unique transaction ID
    trans_ts       TIMESTAMP     NOT NULL,    -- when the transaction happened
    cc_num         TEXT          NOT NULL,    -- card number: an identifier, up to 19 digits
    merchant       TEXT          NOT NULL,
    category       TEXT          NOT NULL,
    amt            NUMERIC(12,2) NOT NULL,    -- exact money type, no floating-point rounding
    first_name     TEXT,                      -- personal fields: kept in the system of record,
    last_name      TEXT,                      -- never used as model features or shown in the app
    gender         CHAR(1),
    street         TEXT,
    city           TEXT,
    state          CHAR(2),
    zip            CHAR(5),
    cust_lat       DOUBLE PRECISION NOT NULL, -- customer's home location
    cust_long      DOUBLE PRECISION NOT NULL,
    city_pop       INTEGER,
    job            TEXT,
    dob            DATE,
    merch_lat      DOUBLE PRECISION NOT NULL, -- where the merchant is
    merch_long     DOUBLE PRECISION NOT NULL,
    is_fraud       SMALLINT      NOT NULL CHECK (is_fraud IN (0, 1)),
    source_file    TEXT          NOT NULL     -- fraudTrain.csv or fraudTest.csv, for row-count checks
);

-- Feature views will look back over each card's history in time order, so index that path.
CREATE INDEX idx_raw_card_time ON raw_transactions (cc_num, trans_ts);
