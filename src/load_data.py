"""Load the Kaggle fraud CSVs into PostgreSQL.

Steps:
  1. Run sql/schema.sql (drops and recreates the raw tables, so reruns are safe).
  2. For each CSV: COPY it into staging_transactions, then INSERT ... SELECT into
     raw_transactions with proper types, then empty staging.
  3. Print row counts per file so they can be checked against the source.

Run from the repo root:  .venv/bin/python src/load_data.py
"""

import os
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
CSV_FILES = ["fraudTrain.csv", "fraudTest.csv"]

# Turns the all-text staging row into a typed raw row.
INSERT_FROM_STAGING = """
INSERT INTO raw_transactions (
    trans_num, trans_ts, cc_num, merchant, category, amt,
    first_name, last_name, gender, street, city, state, zip,
    cust_lat, cust_long, city_pop, job, dob,
    merch_lat, merch_long, is_fraud, source_file
)
SELECT
    trans_num,
    trans_date_trans_time::timestamp,
    cc_num,
    merchant,
    category,
    amt::numeric(12,2),
    first,
    last,
    gender,
    street,
    city,
    state,
    lpad(zip, 5, '0'),          -- restore leading zeros lost in the CSV
    lat::double precision,
    long::double precision,
    city_pop::integer,
    job,
    dob::date,
    merch_lat::double precision,
    merch_long::double precision,
    is_fraud::smallint,
    %(source_file)s
FROM staging_transactions;
"""


def connect() -> psycopg.Connection:
    """Open a connection using the settings in .env."""
    load_dotenv(REPO_ROOT / ".env")
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def load_file(conn: psycopg.Connection, csv_name: str) -> None:
    """Bulk-load one CSV via staging into raw_transactions."""
    csv_path = RAW_DIR / csv_name
    started = time.time()

    with conn.cursor() as cur:
        cur.execute("TRUNCATE staging_transactions;")

        # COPY streams the file straight into PostgreSQL: far faster than row-by-row inserts.
        copy_sql = "COPY staging_transactions FROM STDIN WITH (FORMAT csv, HEADER true)"
        with cur.copy(copy_sql) as copy, open(csv_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                copy.write(chunk)

        cur.execute(INSERT_FROM_STAGING, {"source_file": csv_name})
        loaded = cur.rowcount
        cur.execute("TRUNCATE staging_transactions;")

    conn.commit()
    print(f"{csv_name}: {loaded:,} rows loaded in {time.time() - started:.0f}s")


def main() -> None:
    schema_sql = (REPO_ROOT / "sql" / "schema.sql").read_text()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()

        for csv_name in CSV_FILES:
            load_file(conn, csv_name)

        # Refresh planner statistics so later queries pick good plans.
        with conn.cursor() as cur:
            cur.execute("ANALYZE raw_transactions;")
        conn.commit()


if __name__ == "__main__":
    main()
