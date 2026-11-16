"""SQL feature tests: build the dbt project on a hand-made fixture and compare with hand-worked values.

Needs a running PostgreSQL. It creates and uses its own database (TEST_POSTGRES_DB, default
fraud_ci), so the real data is never touched, and refuses to run against the main database.

Locally:  set -a && . ./.env && set +a && .venv/bin/pytest tests/test_sql_features.py
In CI:    GitHub Actions starts a PostgreSQL service and runs the same command.
"""

import csv
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
TEST_DB = os.environ.get("TEST_POSTGRES_DB", "fraud_ci")
FEATURES = ["hour_of_day", "txn_count_1h", "txn_count_24h", "amt_sum_24h", "small_txn_count_24h",
            "prior_txn_count", "amt_vs_avg", "secs_since_last", "is_new_merchant", "is_new_category",
            "hour_band_share", "amt_vs_category_avg", "spend_24h_vs_daily_avg", "distance_km"]


def conninfo(dbname: str) -> dict:
    return dict(host=os.environ.get("POSTGRES_HOST", "localhost"), port=os.environ.get("POSTGRES_PORT", "5432"),
                user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"], dbname=dbname)


@pytest.fixture(scope="module")
def built_fixture():
    if "POSTGRES_USER" not in os.environ:
        pytest.skip("No database settings: run with the .env loaded, or in CI")
    assert TEST_DB != os.environ.get("POSTGRES_DB"), "The SQL tests must not run against the main database"

    # 1. A fresh, empty test database
    with psycopg.connect(**conninfo(os.environ["POSTGRES_DB"]), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{TEST_DB}"')

    # 2. The raw layer, exactly as production builds it, filled with the fixture
    with psycopg.connect(**conninfo(TEST_DB)) as conn:
        conn.execute((REPO_ROOT / "sql" / "schema.sql").read_text())
        with open(FIXTURES / "raw_transactions.csv") as f:
            rows = list(csv.DictReader(f))
        columns = list(rows[0])
        conn.cursor().executemany(
            f"INSERT INTO raw_transactions ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
            [[r[c] or None for c in columns] for r in rows])

    # 3. dbt build: every model and every dbt test, on the fixture
    dbt = Path(sys.executable).parent / "dbt"
    result = subprocess.run([str(dbt), "build", "--profiles-dir", "."], cwd=REPO_ROOT / "dbt",
                            env={**os.environ, "POSTGRES_DB": TEST_DB}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-4000:]

    with psycopg.connect(**conninfo(TEST_DB)) as conn, conn.cursor() as cur:
        cur.execute(f"""
            SELECT f.trans_num, {', '.join('f.' + c for c in FEATURES)}, r.rules_route, a.age_band, f.card_token
            FROM analytics.fct_transaction_features f
            JOIN analytics.fct_rules_baseline r USING (trans_num)
            JOIN analytics_restricted.fairness_attributes a USING (trans_num)
        """)
        names = [c.name for c in cur.description]
        actual = {row[0]: dict(zip(names, row)) for row in cur.fetchall()}
    with open(FIXTURES / "expected_features.csv") as f:
        expected = {r["trans_num"]: r for r in csv.DictReader(f)}
    return actual, expected, result.stdout


def test_dbt_build_and_dbt_tests_pass(built_fixture):
    _, _, log = built_fixture
    # dbt's summary line, e.g. "Done. PASS=43 WARN=0 ERROR=0 SKIP=0": nothing failed, warned or skipped
    summary = re.search(r"Done\. PASS=(\d+) WARN=(\d+) ERROR=(\d+) SKIP=(\d+)", log)
    assert summary, log[-2000:]
    passed, warned, errored, skipped = map(int, summary.groups())
    assert passed > 30 and warned == errored == skipped == 0


def test_every_payment_reaches_the_feature_table(built_fixture):
    actual, expected, _ = built_fixture
    assert set(actual) == set(expected)


@pytest.mark.parametrize("feature", FEATURES)
def test_feature_matches_hand_calculation(built_fixture, feature):
    actual, expected, _ = built_fixture
    for trans_num, want in expected.items():
        got = actual[trans_num][feature]
        if want[feature] == "":
            assert got is None, f"{trans_num} {feature}: expected empty (no history), got {got}"
        else:
            assert got is not None, f"{trans_num} {feature}: expected {want[feature]}, got empty"
            assert float(got) == pytest.approx(float(want[feature]), abs=1e-3), f"{trans_num} {feature}"


def test_rules_routing(built_fixture):
    actual, expected, _ = built_fixture
    assert {t: actual[t]["rules_route"] for t in expected} == {t: e["rules_route"] for t, e in expected.items()}


def test_age_bands_including_birthdays(built_fixture):
    actual, expected, _ = built_fixture
    assert {t: actual[t]["age_band"] for t in expected} == {t: e["age_band"] for t, e in expected.items()}


def test_card_numbers_are_tokenised(built_fixture):
    actual, _, _ = built_fixture
    tokens = {r["card_token"] for r in actual.values()}
    assert len(tokens) == 4                                      # one token per card
    assert all(len(t) == 64 and not t.startswith("999") for t in tokens)   # a 256-bit hash, not the number
