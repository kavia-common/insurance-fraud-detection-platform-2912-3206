# Supabase Configuration - Claims Database

## Overview
The `claims_database` container manages the PostgreSQL schema hosted on Supabase for the Insurance Fraud Detection Platform.

## Schema Status: ✅ Configured
All 12 tables, 18 indexes, 7 triggers, and 12 RLS policies have been applied.

## Tables
1. `users` - System users with role-based access (admin, manager, investigator)
2. `policyholders` - Insurance policyholder records
3. `policies` - Insurance policy records linked to policyholders
4. `claims` - Insurance claims with fraud scoring and computed risk levels
5. `fraud_rules` - Configurable fraud detection rules engine
6. `fraud_signals` - Per-claim fraud rule evaluation results
7. `investigator_assignments` - Claim-to-investigator assignment tracking
8. `claim_outcomes` - Fraud investigation outcome records
9. `network_relationships` - Entity relationship graph for network visualization
10. `claim_documents` - Document attachments for claims
11. `audit_log` - Compliance audit trail
12. `report_snapshots` - Saved report data

## Seed Data Status: ✅ Loaded
- 3 default users (admin, manager, investigator)
- 6 default fraud detection rules
- 1 sample policyholder, policy, claim with signals, assignment, outcome, and network data

## Migration Scripts
- `scripts/migrate.py` - Creates extensions, enums, tables, indexes, triggers, and RLS policies
- `scripts/seed_data.py` - Populates default fraud rules, users, and sample data
