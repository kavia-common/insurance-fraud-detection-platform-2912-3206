#!/usr/bin/env python3
"""
Seed data script for Insurance Fraud Detection Platform (claims_database).
Populates fraud_rules, users, policyholders, policies, claims, and example network/test data via run_sql RPC.
"""
import json
import os
import sys
import urllib.request

# Config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ayhoidlkvgrsqntjlfew.supabase.co")
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
def run_sql(query, label=None):
    """Runs a SQL statement via Supabase run_sql function RPC."""
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(RPC_URL, data=data, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req)
        print(f"OK: {label or query[:90]}")
        return resp.read().decode()
    except Exception as e:
        msg = e.read().decode() if hasattr(e, 'read') else str(e)
        print(f"ERROR: {label or query[:80]}\n  {msg}")
        return None

def main():
    # Seed admin and investigator users
    users_sql = """
        INSERT INTO users (id, email, full_name, role, department, is_active)
        VALUES
        ('00000000-0000-0000-0000-000000000001', 'admin@insure.com', 'Site Admin', 'admin', 'Admin', true)
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO users (id, email, full_name, role, department, is_active)
        VALUES
        ('00000000-0000-0000-0000-000000000002', 'mgr@insure.com', 'Manager Jane', 'manager', 'SIU', true)
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO users (id, email, full_name, role, department, is_active)
        VALUES
        ('00000000-0000-0000-0000-000000000003', 'inv@insure.com', 'Investigator Bob', 'investigator', 'SIU', true)
        ON CONFLICT (id) DO NOTHING;
    """
    run_sql(users_sql, "Seed users")

    # Seed 5+ fraud rules
    fraud_rules_sql = """
        INSERT INTO fraud_rules (id, rule_name, description, category, condition_config, score_weight, is_active)
        VALUES
        (gen_random_uuid(), 'High Amount', 'Flags claims over $15,000', 'amount', '{"threshold":15000}', 25, true),
        (gen_random_uuid(), 'Quick Filing', 'Claim filed within 2 days of policy', 'timing', '{"days":2}', 18, true),
        (gen_random_uuid(), 'Recent Address Change', 'Policyholder changed address <3m before claim', 'pattern', '{"months":3}', 15, true),
        (gen_random_uuid(), 'Multiple Claims in 6 Months', 'Same holder has >2 claims in 6m', 'frequency', '{"months":6,"count":2}', 20, true),
        (gen_random_uuid(), 'Out-of-State Incident', 'Incident state differs from policyholder', 'location', '{}', 10, true),
        (gen_random_uuid(), 'Known Fraud Network', 'Related to a prior fraudulent network', 'network', '{}', 30, true)
        ON CONFLICT (rule_name) DO NOTHING;
    """
    run_sql(fraud_rules_sql, "Seed fraud_rules")

    # Seed a policyholder and policy
    ph_sql = """
        INSERT INTO policyholders (id, first_name, last_name, email, phone, city, state, date_of_birth)
        VALUES
        ('00000000-0000-0000-0000-000000000010', 'Elena', 'Smith', 'elena.smith@email.com', '2125555555', 'NYC', 'NY', '1975-12-10')
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO policies (id, policy_number, policyholder_id, policy_type, effective_date, expiration_date, premium_amount, coverage_amount)
        VALUES
        ('00000000-0000-0000-0000-000000000020', 'POL123456', '00000000-0000-0000-0000-000000000010', 'Auto', '2023-01-01', '2024-01-01', 800.00, 25000.00)
        ON CONFLICT (id) DO NOTHING;
    """
    run_sql(ph_sql, "Seed policyholder/policy")

    # Seed a sample claim, triggers signals
    claim_sql = """
        INSERT INTO claims (id, claim_number, policy_id, policyholder_id, claim_type, claim_amount, incident_date, filed_date, description, status, fraud_score, assigned_investigator_id)
        VALUES
        ('00000000-0000-0000-0000-000000000100', 'CLM5555', '00000000-0000-0000-0000-000000000020', '00000000-0000-0000-0000-000000000010',
         'Collision', 16000.00, '2023-04-14', '2023-04-15', 'Collision on 5th Ave, minor injuries reported.', 'flagged', 82, '00000000-0000-0000-0000-000000000003')
        ON CONFLICT (id) DO NOTHING;
    """
    run_sql(claim_sql, "Seed single example claim")

    # Seed claim signals for the claim for 3 rules (simulate rules engine)
    signals_sql = """
        INSERT INTO fraud_signals (claim_id, rule_id, triggered, signal_score, explanation)
        SELECT '00000000-0000-0000-0000-000000000100', id, true, 25, 'Claim is above threshold'
        FROM fraud_rules WHERE rule_name = 'High Amount'
        ON CONFLICT DO NOTHING;
        INSERT INTO fraud_signals (claim_id, rule_id, triggered, signal_score, explanation)
        SELECT '00000000-0000-0000-0000-000000000100', id, true, 18, 'Filed quickly after policy'
        FROM fraud_rules WHERE rule_name = 'Quick Filing'
        ON CONFLICT DO NOTHING;
        INSERT INTO fraud_signals (claim_id, rule_id, triggered, signal_score, explanation)
        SELECT '00000000-0000-0000-0000-000000000100', id, false, 0, 'No network match'
        FROM fraud_rules WHERE rule_name = 'Known Fraud Network'
        ON CONFLICT DO NOTHING;
    """
    run_sql(signals_sql, "Seed fraud_signals")

    # Seed assignment
    assign_sql = """
        INSERT INTO investigator_assignments (claim_id, investigator_id, assigned_by, status, priority, assigned_at)
        VALUES
        ('00000000-0000-0000-0000-000000000100', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', 'pending', 1, now())
        ON CONFLICT DO NOTHING;
    """
    run_sql(assign_sql, "Seed investigator assignment")

    # Seed claim outcome
    outcome_sql = """
        INSERT INTO claim_outcomes (claim_id, investigator_id, outcome, recovery_amount, summary, evidence_notes, resolution_date)
        VALUES
        ('00000000-0000-0000-0000-000000000100', '00000000-0000-0000-0000-000000000003', 'confirmed_fraud', 13000.00, 'Fraud confirmed after investigation.', 'Car repair estimate forged; witness recanted', '2023-04-25')
        ON CONFLICT (claim_id) DO NOTHING;
    """
    run_sql(outcome_sql, "Seed claim outcome")

    # Seed a network relationship (policyholder linked to known fraud party)
    network_sql = """
        INSERT INTO network_relationships (entity_a_type, entity_a_id, entity_b_type, entity_b_id, relationship_type, strength)
        VALUES
        ('policyholder', '00000000-0000-0000-0000-000000000010', 'claim', '00000000-0000-0000-0000-000000000100', 'filed', 1.0)
        ON CONFLICT DO NOTHING;
    """
    run_sql(network_sql, "Seed network relationship")

    print("Seed data loaded.")

if __name__ == "__main__":
    main()
