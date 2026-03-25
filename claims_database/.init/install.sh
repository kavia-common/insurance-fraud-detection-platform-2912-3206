#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="/home/kavia/workspace/code-generation/insurance-fraud-detection-platform-2912-3206/claims_database"
cd "$WORKSPACE"
mkdir -p "$WORKSPACE/sql" "$WORKSPACE/scripts" "$WORKSPACE/tests" || true
# Ensure postgres client tools present (idempotent); install package if any missing
for bin in psql pg_dump pg_restore pg_isready; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    sudo apt-get update -q && sudo apt-get install -y -qq postgresql-client || { echo "ERROR: failed to install postgresql-client" >&2; exit 10; }
    break
  fi
done
# Record versions (best-effort)
psql --version > "$WORKSPACE/psql_version.txt" 2>&1 || true
pg_dump --version > "$WORKSPACE/pg_dump_version.txt" 2>&1 || true
pg_restore --version > "$WORKSPACE/pg_restore_version.txt" 2>&1 || true
# Idempotent Python package install helper (robust import/version check)
check_and_install_py() {
  pkg="$1"; min_ver="$2"; mod="$3"
  python3 - <<PYCHECK 2>/dev/null || true
import sys, importlib
try:
    spec = importlib.util.find_spec('$mod')
    if not spec:
        sys.exit(2)
    try:
        import pkg_resources as _pr
        dist = _pr.get_distribution('$pkg')
        if _pr.parse_version(dist.version) < _pr.parse_version('$min_ver'):
            sys.exit(3)
    except Exception:
        pass
    sys.exit(0)
except Exception:
    sys.exit(2)
PYCHECK
  rc=$?
  if [ "$rc" -ne 0 ]; then
    python3 -m pip install --disable-pip-version-check -q "$pkg>=$min_ver"
  fi
}
check_and_install_py "psycopg2-binary" "2.9" "psycopg2"
check_and_install_py "pytest" "7.0" "pytest"
# Write non-secret global defaults (world-readable) - do NOT include POSTGRES_PASSWORD or DATABASE_URL
sudo bash -c 'cat > /etc/profile.d/claims_db_env.sh <<"EOF"
# claims_db non-secret defaults
export POSTGRES_USER="${POSTGRES_USER:-postgres}"
export POSTGRES_DB="${POSTGRES_DB:-claims_db}"
export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
# NOTE: secrets (POSTGRES_PASSWORD) MUST NOT be placed here. Use /root/.claims_db_env (600) via helper.
EOF'
sudo chmod 0644 /etc/profile.d/claims_db_env.sh
# Create root-only secret writer (does NOT get auto-sourced by public loader)
sudo bash -c 'cat > /usr/local/bin/claims_db_write_secret.sh <<"SH"
#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ]; then echo "Usage: sudo $0 '<POSTGRES_PASSWORD>'" >&2; exit 2; fi
mkdir -p /root || true
cat > /root/.claims_db_env <<EOF
export POSTGRES_PASSWORD="$1"
# Optional: export DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$PGHOST:$PGPORT/$POSTGRES_DB"
EOF
chmod 0600 /root/.claims_db_env
echo "/root/.claims_db_env created (600)"
SH'
sudo chmod 0755 /usr/local/bin/claims_db_write_secret.sh
# README update with explicit env guidance
cat > "$WORKSPACE/README.md" <<'MD'
Required env for headless runs (set in CI or via sudo helper):
  POSTGRES_USER (default: postgres)
  POSTGRES_DB   (default: claims_db)
  PGHOST        (default: localhost)
  PGPORT        (default: 5432)
If password auth is required, run as root:
  sudo /usr/local/bin/claims_db_write_secret.sh 'yourpassword'
This writes /root/.claims_db_env (600). The public loader does NOT source root secrets automatically — automation must export DATABASE_URL in the current session or source /root/.claims_db_env with appropriate privileges.
MD

# Final verification: list created files (minimal output)
ls -ld "$WORKSPACE"/sql "$WORKSPACE"/scripts "$WORKSPACE"/tests >/dev/null 2>&1 || true
[ -f /etc/profile.d/claims_db_env.sh ] || { echo "ERROR: /etc/profile.d/claims_db_env.sh missing" >&2; exit 20; }
[ -f /usr/local/bin/claims_db_write_secret.sh ] || { echo "ERROR: secret helper missing" >&2; exit 21; }
exit 0
