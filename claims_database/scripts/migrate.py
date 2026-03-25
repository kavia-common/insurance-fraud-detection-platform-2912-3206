#!/usr/bin/env python3
"""
Database migration script for the Insurance Fraud Detection Platform.
Executes DDL statements against Supabase via the run_sql RPC function.
Creates all tables, indexes, RLS policies, and seed data.
"""
import json
import os
import sys
import urllib.request

# Configuration from environment or defaults
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://ayhoidlkvgrsqntjlfew.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF5aG9pZGxrdmdyc3FudGpsZmV3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ0NTY4NTcsImV4cCI6MjA5MDAzMjg1N30.SsXv2PerBu8_H2TIlc8f7dzezD5l6tb53VPsNxpdaBw",
)

RPC_URL = f"{SUPABASE_URL}/rest/v1/rpc/run_sql"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


# PUBLIC_INTERFACE
def run_sql(query, label=""):
    """Execute a single SQL statement via Supabase run_sql RPC.

    Args:
        query: SQL statement to execute.
        label: Human-readable label for logging.

    Returns:
        True if successful, False otherwise.
    """
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(RPC_URL, data=data, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req)
        result = resp.read().decode()
        tag = label or query[:80]
        print(f"  OK: {tag}")
        return True
    except Exception as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        tag = label or query[:80]
        print(f"  ERROR: {tag} => {err}")
        return False


# ---------------------------------------------------------------------------
# SQL statements grouped by category
# ---------------------------------------------------------------------------

EXTENSIONS_SQL = [
    ('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"', "Enable uuid-ossp"),
    ("CREATE EXTENSION IF NOT EXISTS pgcrypto", "Enable pgcrypto"),
]

ENUM_SQL = [
    (
        """DO $$ BEGIN
    CREATE TYPE claim_status AS ENUM (
        'new','under_review','flagged','investigating',
        'closed_confirmed_fraud','closed_legitimate','closed_insufficient_evidence'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""",
        "Create claim_status enum",
    ),
    (
        """DO $$ BEGIN
    CREATE TYPE assignment_status AS ENUM (
        'pending','accepted','in_progress','completed','reassigned'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""",
        "Create assignment_status enum",
    ),
    (
        """DO $$ BEGIN
    CREATE TYPE fraud_outcome_type AS ENUM (
        'confirmed_fraud','legitimate','insufficient_evidence',
        'referred_to_law_enforcement','pending'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""",
        "Create fraud_outcome_type enum",
    ),
    (
        """DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('investigator','manager','admin');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""",
        "Create user_role enum",
    ),
    (
        """DO $$ BEGIN
    CREATE TYPE rule_category AS ENUM (
        'amount','frequency','timing','location','pattern','network','custom'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""",
        "Create rule_category enum",
    ),
]

TABLES_SQL = [
    # 1. users
    (
        """CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'investigator',
    department TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    max_caseload INTEGER DEFAULT 20,
    current_caseload INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create users table",
    ),
    # 2. policyholders
    (
        """CREATE TABLE IF NOT EXISTS policyholders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    date_of_birth DATE,
    ssn_last_four TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create policyholders table",
    ),
    # 3. policies
    (
        """CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number TEXT UNIQUE NOT NULL,
    policyholder_id UUID REFERENCES policyholders(id) ON DELETE CASCADE,
    policy_type TEXT NOT NULL,
    effective_date DATE NOT NULL,
    expiration_date DATE,
    premium_amount NUMERIC(12,2),
    coverage_amount NUMERIC(14,2),
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create policies table",
    ),
    # 4. claims
    (
        """CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_number TEXT UNIQUE NOT NULL,
    policy_id UUID REFERENCES policies(id) ON DELETE SET NULL,
    policyholder_id UUID REFERENCES policyholders(id) ON DELETE SET NULL,
    claim_type TEXT NOT NULL,
    claim_amount NUMERIC(14,2) NOT NULL,
    incident_date DATE NOT NULL,
    filed_date DATE NOT NULL DEFAULT CURRENT_DATE,
    description TEXT,
    status claim_status NOT NULL DEFAULT 'new',
    fraud_score INTEGER DEFAULT 0 CHECK (fraud_score >= 0 AND fraud_score <= 100),
    risk_level TEXT GENERATED ALWAYS AS (
        CASE
            WHEN fraud_score >= 75 THEN 'high'
            WHEN fraud_score >= 40 THEN 'medium'
            ELSE 'low'
        END
    ) STORED,
    location TEXT,
    police_report_filed BOOLEAN DEFAULT false,
    police_report_number TEXT,
    witnesses INTEGER DEFAULT 0,
    assigned_investigator_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ingestion_source TEXT DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create claims table",
    ),
    # 5. fraud_rules (configurable rules engine)
    (
        """CREATE TABLE IF NOT EXISTS fraud_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    category rule_category NOT NULL DEFAULT 'custom',
    condition_config JSONB NOT NULL DEFAULT '{}',
    score_weight INTEGER NOT NULL DEFAULT 10 CHECK (score_weight >= 0 AND score_weight <= 100),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create fraud_rules table",
    ),
    # 6. fraud_signals (per-claim rule results)
    (
        """CREATE TABLE IF NOT EXISTS fraud_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    rule_id UUID NOT NULL REFERENCES fraud_rules(id) ON DELETE CASCADE,
    triggered BOOLEAN NOT NULL DEFAULT false,
    signal_score INTEGER NOT NULL DEFAULT 0,
    explanation TEXT,
    details JSONB DEFAULT '{}',
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create fraud_signals table",
    ),
    # 7. investigator_assignments
    (
        """CREATE TABLE IF NOT EXISTS investigator_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    investigator_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    status assignment_status NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    notes TEXT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create investigator_assignments table",
    ),
    # 8. claim_outcomes (fraud investigation results)
    (
        """CREATE TABLE IF NOT EXISTS claim_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID UNIQUE NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    investigator_id UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    outcome fraud_outcome_type NOT NULL DEFAULT 'pending',
    recovery_amount NUMERIC(14,2) DEFAULT 0,
    summary TEXT,
    evidence_notes TEXT,
    resolution_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create claim_outcomes table",
    ),
    # 9. network_relationships (for network/relationship views)
    (
        """CREATE TABLE IF NOT EXISTS network_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_a_type TEXT NOT NULL,
    entity_a_id UUID NOT NULL,
    entity_b_type TEXT NOT NULL,
    entity_b_id UUID NOT NULL,
    relationship_type TEXT NOT NULL,
    strength NUMERIC(5,2) DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create network_relationships table",
    ),
    # 10. claim_documents (attachments and evidence)
    (
        """CREATE TABLE IF NOT EXISTS claim_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    document_name TEXT NOT NULL,
    document_type TEXT,
    file_path TEXT,
    file_size INTEGER,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create claim_documents table",
    ),
    # 11. audit_log (track actions for compliance)
    (
        """CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    old_values JSONB,
    new_values JSONB,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create audit_log table",
    ),
    # 12. report_snapshots (manager reporting)
    (
        """CREATE TABLE IF NOT EXISTS report_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type TEXT NOT NULL,
    generated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    filters JSONB DEFAULT '{}',
    data JSONB NOT NULL DEFAULT '{}',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        "Create report_snapshots table",
    ),
]

INDEXES_SQL = [
    ("CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status)", "Index claims.status"),
    ("CREATE INDEX IF NOT EXISTS idx_claims_fraud_score ON claims(fraud_score DESC)", "Index claims.fraud_score"),
    ("CREATE INDEX IF NOT EXISTS idx_claims_policy_id ON claims(policy_id)", "Index claims.policy_id"),
    ("CREATE INDEX IF NOT EXISTS idx_claims_policyholder_id ON claims(policyholder_id)", "Index claims.policyholder_id"),
    ("CREATE INDEX IF NOT EXISTS idx_claims_assigned_investigator ON claims(assigned_investigator_id)", "Index claims.assigned_investigator_id"),
    ("CREATE INDEX IF NOT EXISTS idx_claims_filed_date ON claims(filed_date DESC)", "Index claims.filed_date"),
    ("CREATE INDEX IF NOT EXISTS idx_fraud_signals_claim_id ON fraud_signals(claim_id)", "Index fraud_signals.claim_id"),
    ("CREATE INDEX IF NOT EXISTS idx_fraud_signals_rule_id ON fraud_signals(rule_id)", "Index fraud_signals.rule_id"),
    ("CREATE INDEX IF NOT EXISTS idx_assignments_investigator ON investigator_assignments(investigator_id)", "Index assignments.investigator_id"),
    ("CREATE INDEX IF NOT EXISTS idx_assignments_claim ON investigator_assignments(claim_id)", "Index assignments.claim_id"),
    ("CREATE INDEX IF NOT EXISTS idx_assignments_status ON investigator_assignments(status)", "Index assignments.status"),
    ("CREATE INDEX IF NOT EXISTS idx_outcomes_claim ON claim_outcomes(claim_id)", "Index outcomes.claim_id"),
    ("CREATE INDEX IF NOT EXISTS idx_network_entity_a ON network_relationships(entity_a_type, entity_a_id)", "Index network.entity_a"),
    ("CREATE INDEX IF NOT EXISTS idx_network_entity_b ON network_relationships(entity_b_type, entity_b_id)", "Index network.entity_b"),
    ("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id)", "Index audit.entity"),
    ("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)", "Index audit.user_id"),
    ("CREATE INDEX IF NOT EXISTS idx_policies_policyholder ON policies(policyholder_id)", "Index policies.policyholder_id"),
    ("CREATE INDEX IF NOT EXISTS idx_documents_claim ON claim_documents(claim_id)", "Index documents.claim_id"),
]

# Updated_at trigger function
TRIGGER_SQL = [
    (
        """CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql""",
        "Create updated_at trigger function",
    ),
]

# Tables that need updated_at triggers
TRIGGER_TABLES = [
    "users", "policyholders", "policies", "claims",
    "fraud_rules", "investigator_assignments", "claim_outcomes",
]

RLS_SQL = [
    ("ALTER TABLE users ENABLE ROW LEVEL SECURITY", "Enable RLS on users"),
    ("ALTER TABLE claims ENABLE ROW LEVEL SECURITY", "Enable RLS on claims"),
    ("ALTER TABLE policies ENABLE ROW LEVEL SECURITY", "Enable RLS on policies"),
    ("ALTER TABLE policyholders ENABLE ROW LEVEL SECURITY", "Enable RLS on policyholders"),
    ("ALTER TABLE fraud_rules ENABLE ROW LEVEL SECURITY", "Enable RLS on fraud_rules"),
    ("ALTER TABLE fraud_signals ENABLE ROW LEVEL SECURITY", "Enable RLS on fraud_signals"),
    ("ALTER TABLE investigator_assignments ENABLE ROW LEVEL SECURITY", "Enable RLS on investigator_assignments"),
    ("ALTER TABLE claim_outcomes ENABLE ROW LEVEL SECURITY", "Enable RLS on claim_outcomes"),
    ("ALTER TABLE network_relationships ENABLE ROW LEVEL SECURITY", "Enable RLS on network_relationships"),
    ("ALTER TABLE claim_documents ENABLE ROW LEVEL SECURITY", "Enable RLS on claim_documents"),
    ("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY", "Enable RLS on audit_log"),
    ("ALTER TABLE report_snapshots ENABLE ROW LEVEL SECURITY", "Enable RLS on report_snapshots"),
    # Allow anon/authenticated to read/write for now (backend handles auth)
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_users ON users FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on users"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_claims ON claims FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on claims"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_policies ON policies FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on policies"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_policyholders ON policyholders FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on policyholders"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_fraud_rules ON fraud_rules FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on fraud_rules"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_fraud_signals ON fraud_signals FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on fraud_signals"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_assignments ON investigator_assignments FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on investigator_assignments"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_outcomes ON claim_outcomes FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on claim_outcomes"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_network ON network_relationships FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on network_relationships"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_documents ON claim_documents FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on claim_documents"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_audit ON audit_log FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on audit_log"),
    ("""DO $$ BEGIN
    CREATE POLICY anon_all_reports ON report_snapshots FOR ALL TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$""", "RLS policy: anon all on report_snapshots"),
]


# PUBLIC_INTERFACE
def run_migration():
    """Run the full database migration: extensions, enums, tables, indexes, triggers, RLS, and seed data.

    Returns:
        Tuple of (success_count, error_count).
    """
    success = 0
    errors = 0

    sections = [
        ("Extensions", EXTENSIONS_SQL),
        ("Enums", ENUM_SQL),
        ("Tables", TABLES_SQL),
        ("Indexes", INDEXES_SQL),
        ("Trigger Functions", TRIGGER_SQL),
        ("RLS Policies", RLS_SQL),
    ]

    for section_name, statements in sections:
        print(f"\n=== {section_name} ===")
        for sql, label in statements:
            if run_sql(sql, label):
                success += 1
            else:
                errors += 1

    # Create triggers for updated_at on each table
    print("\n=== Updated_at Triggers ===")
    for tbl in TRIGGER_TABLES:
        sql = f"""DO $$ BEGIN
    CREATE TRIGGER set_updated_at_{tbl}
        BEFORE UPDATE ON {tbl}
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$"""
        if run_sql(sql, f"Trigger updated_at on {tbl}"):
            success += 1
        else:
            errors += 1

    return success, errors


if __name__ == "__main__":
    print("=" * 60)
    print("Insurance Fraud Detection Platform - Database Migration")
    print("=" * 60)
    s, e = run_migration()
    print(f"\n{'=' * 60}")
    print(f"Migration complete: {s} succeeded, {e} failed")
    if e > 0:
        sys.exit(1)
    print("Schema ready.")
