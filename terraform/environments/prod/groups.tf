# terraform/environments/prod/groups.tf
# ─────────────────────────────────────────────────────────────────────────────
# Azure AD groups required for this workspace.
#
# These groups must be created manually in Azure AD and configured for
# SCIM provisioning to this Databricks workspace. Terraform references them
# by display name once SCIM has synced them in.
#
# Groups to create in Azure AD:
#   dbx-metastore-admins       — Unity Catalog metastore administrators
#   dbx-workspace-admins       — Databricks workspace administrators
#   dbx-admins                 — General Databricks admins
#   dbx-platform-engineers     — Platform engineering team
#   dbx-data-engineers         — Data engineering (all domains)
#   dbx-data-analysts          — Read-only analysts
#   dbx-data-scientists        — ML/data science team
#   dbx-ecommerce-data-engineers — Ecommerce domain engineers
#   dbx-finance-data-engineers   — Finance domain engineers
#   dbx-finance-analysts         — Finance read-only analysts
# ─────────────────────────────────────────────────────────────────────────────

locals {
  groups = {
    metastore_admins = "dbx-metastore-admins"
  }
}
