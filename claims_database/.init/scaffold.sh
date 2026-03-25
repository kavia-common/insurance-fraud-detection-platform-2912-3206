#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="/home/kavia/workspace/code-generation/insurance-fraud-detection-platform-2912-3206/claims_database"
mkdir -p "$WORKSPACE/sql" "$WORKSPACE/scripts"
# SQL scaffold
cat > "$WORKSPACE/sql/00_schema.sql" <<'SQL'
-- Idempotent schema and table creation; set app_role via psql --set=app_role=role
\set app_role ''''current_user''''
DO $$ DECLARE
  _app_role text := (CASE WHEN current_setting('app.app_role', true) IS NULL THEN NULL ELSE :'app_role' END);
BEGIN
  IF _app_role IS NOT NULL THEN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION %I', _app_role);
  ELSE
    CREATE SCHEMA IF NOT EXISTS app;
  END IF;
EXCEPTION WHEN others THEN
  CREATE SCHEMA IF NOT EXISTS app;
END$$;
-- Attempt to create extensions if permitted (idempotent)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Create table if not exists
CREATE TABLE IF NOT EXISTS app.claims (
  id uuid PRIMARY KEY,
  policy_number text NOT NULL,
  amount numeric(12,2) NOT NULL,
  status text NOT NULL DEFAULT 'new',
  created_at timestamptz DEFAULT now()
);
-- Conditionally set default for id using available uuid function
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'gen_random_uuid') THEN
    ALTER TABLE app.claims ALTER COLUMN id SET DEFAULT gen_random_uuid();
  ELSIF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'uuid_generate_v4') THEN
    ALTER TABLE app.claims ALTER COLUMN id SET DEFAULT uuid_generate_v4();
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'Could not set id default: %', SQLERRM;
END$$;
-- Note: run psql with --set=app_role=username to set ownership explicitly
SQL

# Healthcheck script using pg_isready with explicit flags
cat > "$WORKSPACE/scripts/healthcheck.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="/home/kavia/workspace/code-generation/insurance-fraud-detection-platform-2912-3206/claims_database"
# Load public defaults (non-secret)
[ -f /etc/profile.d/claims_db_env.sh ] && . /etc/profile.d/claims_db_env.sh || true
# If running as root, optionally source root-only secrets
if [ "$(id -u)" -eq 0 ] && [ -f /root/.claims_db_env ]; then
  # shellcheck disable=SC1090
  . /root/.claims_db_env
fi
HOST="${PGHOST:-localhost}"
PORT="${PGPORT:-5432}"
DB="${POSTGRES_DB:-claims_db}"
USER="${POSTGRES_USER:-postgres}"
RETRIES="${HEALTH_RETRIES:-5}"
SLEEP="${HEALTH_SLEEP:-1}"
if command -v pg_isready >/dev/null 2>&1; then
  i=0
  while [ "$i" -lt "$RETRIES" ]; do
    if pg_isready -h "$HOST" -p "$PORT" -d "$DB" -U "$USER" >/dev/null 2>&1; then
      exit 0
    fi
    i=$((i+1))
    sleep "$SLEEP"
  done
  exit 2
else
  # Fallback to a minimal psql probe using flags (avoid raw URI when possible)
  if command -v psql >/dev/null 2>&1; then
    if PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -Atc 'SELECT 1' >/dev/null 2>&1; then
      exit 0
    fi
  fi
  exit 2
fi
SH
chmod +x "$WORKSPACE/scripts/healthcheck.sh"

# CSV import helper: safe schema.table handling, uses psycopg2.sql for identifiers, logs to workspace
cat > "$WORKSPACE/scripts/csv_import.py" <<'PY'
#!/usr/bin/env python3
import os, sys, csv, logging
from psycopg2 import connect, sql, OperationalError

LOG_PATH = os.path.join(os.path.dirname(__file__), 'csv_import.log')
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
DB = os.environ.get('DATABASE_URL')
if not DB:
    logging.error('DATABASE_URL not set')
    print('DATABASE_URL not set', file=sys.stderr)
    sys.exit(2)
if len(sys.argv) < 2:
    print('Usage: csv_import.py <csv-file> [schema.table]')
    sys.exit(2)
csv_file = sys.argv[1]
target = sys.argv[2] if len(sys.argv) > 2 else 'app.claims'
if '.' in target:
    schema, table = target.split('.', 1)
else:
    schema, table = 'public', target
# columns expected for COPY (order matters)
cols = ['policy_number', 'amount', 'status', 'created_at']
conn = None
try:
    conn = connect(DB)
    conn.autocommit = False
    with conn.cursor() as cur, open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError('empty csv')
        hdr_lower = [h.strip().lower() for h in header]
        # require at least these core columns
        required = cols[:3]
        if not all(col in hdr_lower for col in required):
            raise ValueError('CSV missing required columns: ' + ','.join(required))
        # Prepare safe COPY statement using identifiers
        stmt = sql.SQL('COPY {}.{} ({}) FROM STDIN WITH CSV HEADER').format(
            sql.Identifier(schema), sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, cols))
        )
        f.seek(0)
        cur.copy_expert(stmt, f)
    conn.commit()
    print('imported')
    logging.info('import succeeded: %s -> %s.%s', csv_file, schema, table)
except Exception as e:
    if conn:
        try:
            conn.rollback()
        except Exception:
            pass
    logging.exception('import failed for %s -> %s.%s: %s', csv_file, schema, table, e)
    print('import failed: %s' % e, file=sys.stderr)
    sys.exit(3)
finally:
    if conn:
        try:
            conn.close()
        except Exception:
            pass
PY
chmod +x "$WORKSPACE/scripts/csv_import.py"

# Print short success marker
printf 'scaffold: created sql/00_schema.sql scripts/healthcheck.sh scripts/csv_import.py\n'
