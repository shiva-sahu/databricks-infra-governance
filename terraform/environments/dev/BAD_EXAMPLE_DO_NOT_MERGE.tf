# terraform/environments/dev/BAD_EXAMPLE_DO_NOT_MERGE.tf
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️  THIS FILE IS THE DEMO "BAD PR" ⚠️
#
# This file intentionally violates FOUR governance rules:
#
#   1. ALL PRIVILEGES grant         → blocked by test_permissions.py
#   2. CamelCase catalog name       → blocked by test_naming.py
#   3. Individual user grant        → blocked by test_permissions.py
#   4. Non-standard schema layer    → blocked by test_naming.py
#
# DEMO INSTRUCTIONS:
#   git checkout -b demo/bad-pr
#   git add this file
#   git commit -m "feat: add EcommerceData catalog with analyst access"
#   git push origin demo/bad-pr
#   Open PR → base: dev
#   Watch governance-check.yml fail with clear violation messages
#
# This is exactly what happens when a well-meaning engineer bypasses the process.
# The governance tests catch it before it reaches the workspace.
# ─────────────────────────────────────────────────────────────────────────────

# VIOLATION 1: CamelCase catalog name
# Should be: "dev_ecommerce_orders" — governed by test_naming.py::TestCatalogNaming
resource "databricks_catalog" "bad_catalog" {
  name         = "EcommerceData"   # ← WRONG: CamelCase, missing env prefix
  metastore_id = var.metastore_id
  comment      = "Quick catalog I need for the demo"
  owner        = "data_analysts"
}

# VIOLATION 2: ALL PRIVILEGES grant
# Should use explicit privilege list — governed by test_permissions.py::TestNoAllPrivileges
resource "databricks_grants" "bad_grant" {
  catalog = databricks_catalog.bad_catalog.name

  grant {
    principal  = "data_analysts"
    privileges = ["ALL PRIVILEGES"]  # ← WRONG: forbidden, escalates beyond read-only
  }

  # VIOLATION 3: Individual user grant
  grant {
    principal  = "jane.smith@company.com"  # ← WRONG: individual, not a group
    privileges = ["USE_CATALOG", "SELECT"]
  }
}

# VIOLATION 4: Non-standard schema layer name
# Should be: "orders_bronze" or "orders_silver" — governed by test_naming.py::TestSchemaNaming
resource "databricks_schema" "bad_schema" {
  catalog_name = databricks_catalog.bad_catalog.name
  name         = "orders_raw"  # ← WRONG: 'raw' is not a valid medallion layer
  comment      = "Raw orders data"
  owner        = "data_analysts"
}

# ─────────────────────────────────────────────────────────────────────────────
# WHAT THE GOVERNANCE CHECK WILL OUTPUT:
#
# FAILED tests/governance/test_permissions.py::TestNoAllPrivileges::test_no_all_privileges_in_catalog_grants
# 🚨 ALL PRIVILEGES DETECTED — THIS MERGE IS BLOCKED:
#
#   FAIL  [terraform/environments/dev/BAD_EXAMPLE_DO_NOT_MERGE.tf:34]
#         Line: privileges = ["ALL PRIVILEGES"]
#         'ALL PRIVILEGES' is forbidden. Use explicit privilege lists.
#
# FAILED tests/governance/test_permissions.py::TestProductionBoundaries::test_no_individual_user_grants
# 🚨 INDIVIDUAL USER GRANTS DETECTED:
#
#   FAIL  [terraform/environments/dev/BAD_EXAMPLE_DO_NOT_MERGE.tf:40]
#         Individual user grant detected: principal  = "jane.smith@company.com"
#
# FAILED tests/governance/test_naming.py::TestCatalogNaming::test_catalog_names_follow_convention
# 🚨 CATALOG NAMING VIOLATIONS FOUND:
#
#   FAIL  [terraform/environments/dev/BAD_EXAMPLE_DO_NOT_MERGE.tf:18]
#         Catalog name 'EcommerceData' violates convention.
#
# FAILED tests/governance/test_naming.py::TestSchemaNaming::test_schema_names_follow_medallion_convention
# 🚨 SCHEMA NAMING VIOLATIONS:
#
#   FAIL  [terraform/environments/dev/BAD_EXAMPLE_DO_NOT_MERGE.tf:47]
#         Schema name 'orders_raw' violates medallion convention.
#         Expected: {domain}_{bronze|silver|gold}
# ─────────────────────────────────────────────────────────────────────────────
