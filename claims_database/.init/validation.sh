#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="/home/kavia/workspace/code-generation/insurance-fraud-detection-platform-2912-3206/claims_database"
cd "$WORKSPACE"
# Load non-secret defaults if present (world-readable)
[ -f /etc/profile.d/claims_db_env.sh ] && . /etc/profile.d/claims_db_env.sh || true
# If running as root allow loading root-only secrets (do not expose them publicly)
if [ "$(id -u)" -eq 0 ] && [ -f /root/.claims_db_env ]; then
  # shellcheck disable=SC1090
  . /root/.claims_db_env
fi
HOST="${PGHOST:-localhost}"
PORT="${PGPORT:-5432}"
DB="${POSTGRES_DB:-claims_db}"
USER="${POSTGRES_USER:-postgres}"
# Ensure required client binaries exist
for bin in psql pg_dump pg_restore pg_isready; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "{\"validation\":\"failed\",\"reason\":\"missing_binary:$bin\",\"howto\":\"Install $bin (postgresql-client) inside the container\"}" > "$WORKSPACE/validation_result.json"
    cat "$WORKSPACE/validation_result.json"
    exit 10
  fi
done
# Fail-fast if Postgres not reachable
if ! pg_isready -h "$HOST" -p "$PORT" -d "$DB" -U "$USER" >/dev/null 2>&1; then
  echo '{"validation":"failed","reason":"Postgres not reachable","howto":"Ensure Postgres server is running and reachable at PGHOST/PGPORT and credentials available (export DATABASE_URL or use sudo /usr/local/bin/claims_db_write_secret.sh)."}' > "$WORKSPACE/validation_result.json"
  cat "$WORKSPACE/validation_result.json"
  exit 20
fi
# Build in-session DATABASE_URL (do not write password into world files)
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${HOST}:${PORT}/${DB}"
else
  DATABASE_URL="postgresql://${POSTGRES_USER}@${HOST}:${PORT}/${DB}"
fi
export DATABASE_URL
# Apply schema using psql with --set for app_role; capture output
PSQL_LOG="$WORKSPACE/psql_apply.log"
if ! psql "$DATABASE_URL" --set=app_role="${POSTGRES_USER:-$USER}" -f "$WORKSPACE/sql/00_schema.sql" > "$PSQL_LOG" 2>&1; then
  echo '{"validation":"failed","reason":"psql apply failed","log":"psql_apply.log"}' > "$WORKSPACE/validation_result.json"
  cat "$WORKSPACE/validation_result.json"
  exit 21
fi
# Record extensions and id default (best-effort)
psql "$DATABASE_URL" -Atc "SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto','uuid-ossp');" > "$WORKSPACE/extensions_present.txt" 2>&1 || true
psql "$DATABASE_URL" -Atc "SELECT column_default FROM information_schema.columns WHERE table_schema='app' AND table_name='claims' AND column_name='id';" > "$WORKSPACE/id_default.txt" 2>&1 || true
# Attempt to create temporary DB for restore validation
TMP_DB="claims_validation_tmp_$(date +%s)"
RUN_RESTORE=0
if psql "$DATABASE_URL" -c "CREATE DATABASE \"$TMP_DB\";" >/dev/null 2>&1; then
  RUN_RESTORE=1
else
  echo '{"validation":"skipped_restore","reason":"cannot create temp DB (insufficient privileges)'}' > "$WORKSPACE/validation_result.json"
  # continue to run dump/tests and append evidence later
fi
# Dump current DB (custom format)
DUMP_FILE="$WORKSPACE/claims_dump.dump"
if ! pg_dump --dbname="$DATABASE_URL" -Fc -f "$DUMP_FILE" >/dev/null 2>&1; then
  echo '{"validation":"failed","reason":"pg_dump failed"}' > "$WORKSPACE/validation_result.json"; cat "$WORKSPACE/validation_result.json"; exit 22
fi
[ -s "$DUMP_FILE" ] || { echo '{"validation":"failed","reason":"dump empty"}' > "$WORKSPACE/validation_result.json"; cat "$WORKSPACE/validation_result.json"; exit 23; }
# Restore into temp DB if created
if [ "$RUN_RESTORE" -eq 1 ]; then
  if ! pg_restore --dbname="postgresql://${POSTGRES_USER:-postgres}@${HOST}:${PORT}/$TMP_DB" -j1 "$DUMP_FILE" >/dev/null 2>&1; then
    psql "$DATABASE_URL" -c "DROP DATABASE IF EXISTS \"$TMP_DB\";" >/dev/null 2>&1 || true
    echo '{"validation":"failed","reason":"pg_restore failed"}' > "$WORKSPACE/validation_result.json"; cat "$WORKSPACE/validation_result.json"; exit 24
  fi
  # cleanup temp DB
  psql "$DATABASE_URL" -c "DROP DATABASE IF EXISTS \"$TMP_DB\";" >/dev/null 2>&1 || true
fi
# Run pytest smoke test and capture output
PYTEST_LOG="$WORKSPACE/tests/pytest_run.log"
if ! python3 -m pytest -q "$WORKSPACE/tests/test_smoke_db.py" | tee "$PYTEST_LOG"; then
  echo '{"validation":"failed","reason":"tests failed","pytest_log":"tests/pytest_run.log"}' > "$WORKSPACE/validation_result.json"
  cat "$WORKSPACE/validation_result.json"
  exit 25
fi
# Success: compose evidence JSON (safe content only)
EXTS="$(cat "$WORKSPACE/extensions_present.txt" 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
IDDEF="$(cat "$WORKSPACE/id_default.txt" 2>/dev/null || true)"
cat > "$WORKSPACE/validation_result.json" <<JSON
{"validation":"success","dump":"$DUMP_FILE","psql_apply_log":"$PSQL_LOG","pytest_log":"$PYTEST_LOG","extensions":"$EXTS","id_default":"$IDDEF","ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
JSON
cat "$WORKSPACE/validation_result.json"
