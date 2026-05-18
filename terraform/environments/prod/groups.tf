# terraform/environments/prod/groups.tf
# ─────────────────────────────────────────────────────────────────────────────
# Azure AD security groups for Databricks.
# These groups are synced to Databricks via SCIM provisioning.
# Membership is managed in Azure AD — Terraform controls existence only.
# ─────────────────────────────────────────────────────────────────────────────

locals {
  # All groups keyed by a logical name → Azure AD display name
  ad_groups = {
    # ── New admin groups ───────────────────────────────────────────────────────
    metastore_admins   = "dbx-metastore-admins"
    workspace_admins   = "dbx-workspace-admins"

    # ── Existing platform groups ───────────────────────────────────────────────
    dbx_admins         = "dbx-admins"
    platform_engineers = "dbx-platform-engineers"

    # ── Data roles ────────────────────────────────────────────────────────────
    data_engineers     = "dbx-data-engineers"
    data_analysts      = "dbx-data-analysts"
    data_scientists    = "dbx-data-scientists"

    # ── Domain groups ─────────────────────────────────────────────────────────
    ecommerce_data_engineers = "dbx-ecommerce-data-engineers"
    finance_data_engineers   = "dbx-finance-data-engineers"
    finance_analysts         = "dbx-finance-analysts"
  }
}

resource "azuread_group" "databricks" {
  for_each = local.ad_groups

  display_name     = each.value
  security_enabled = true
  mail_enabled     = false

  lifecycle {
    # Prevent accidental deletion of groups that may have members
    prevent_destroy = true
  }
}
