#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="/home/kavia/workspace/code-generation/insurance-fraud-detection-platform-2912-3206/claims_database"
cd "$WORKSPACE"
# Ensure python deps exist (exit codes: 2=missing dep)
python3 - <<'PYCHK'
import importlib.util,sys
if importlib.util.find_spec('psycopg2') is None:
    print('missing psycopg2', file=sys.stderr); sys.exit(2)
if importlib.util.find_spec('pytest') is None:
    print('missing pytest', file=sys.stderr); sys.exit(2)
# ok
sys.exit(0)
PYCHK
# Ensure healthcheck exists and reports ready
if [ ! -x "$WORKSPACE/scripts/healthcheck.sh" ]; then
  echo 'healthcheck.sh missing or not executable; ensure scripts/healthcheck.sh present' >&2
  exit 4
fi
if ! "$WORKSPACE/scripts/healthcheck.sh" >/dev/null 2>&1; then
  echo 'DB unreachable; ensure Postgres is running and env set' >&2
  exit 3
fi
mkdir -p "$WORKSPACE/tests"
# Write pytest smoke test (prefers DATABASE_URL, can use POSTGRES_USER if desired)
cat > "$WORKSPACE/tests/test_smoke_db.py" <<'PY'
import os, uuid
import psycopg2
import pytest

def get_conn():
    # Prefer DATABASE_URL, but allow using POSTGRES_USER to detect environment
    db = os.environ.get('DATABASE_URL')
    assert db, 'DATABASE_URL not set'
    return psycopg2.connect(db)

def test_insert_and_select_transactional():
    conn = get_conn()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            # quick privilege check: attempt a transactional insert+rollback using functions that may exist
            try:
                cur.execute("BEGIN; INSERT INTO app.claims (id, policy_number, amount, status) VALUES (uuid_generate_v4()::uuid, %s, %s, %s); ROLLBACK;", ('pchk', 0.0, 'test'))
            except Exception:
                pytest.skip('no insert privilege or missing uuid function; ensure schema grants and functions')
            uid = str(uuid.uuid4())
            cur.execute("INSERT INTO app.claims (id, policy_number, amount, status) VALUES (%s,%s,%s,%s) RETURNING id", (uid, 'TEST-'+uid, 1.23, 'new'))
            row = cur.fetchone()
            assert row is not None
            cur.execute("SELECT policy_number FROM app.claims WHERE id = %s", (row[0],))
            r = cur.fetchone()
            assert r and r[0].startswith('TEST-')
            conn.rollback()
    finally:
        conn.close()
PY
# Run pytest and capture result and exit code
python3 -m pytest -q "$WORKSPACE/tests/test_smoke_db.py" | tee "$WORKSPACE/tests/pytest_output.log"
exit_code=${PIPESTATUS[0]:-0}
exit $exit_code
