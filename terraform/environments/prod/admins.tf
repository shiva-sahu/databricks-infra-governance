# terraform/environments/prod/admins.tf
# ─────────────────────────────────────────────────────────────────────────────
# Databricks-side permissions for the Azure AD admin groups.
#
# Group MEMBERSHIP is managed in Azure AD (by IT admins), not here.
# Terraform creates the groups (groups.tf) and grants them permissions below.
# SCIM provisioning syncs members from Azure AD into Databricks automatically.
# ─────────────────────────────────────────────────────────────────────────────

# ── Metastore grants for dbx-metastore-admins ─────────────────────────────────

resource "databricks_grants" "metastore_admin" {
  metastore = var.metastore_id

  grant {
    principal = azuread_group.databricks["metastore_admins"].display_name
    privileges = [
      "CREATE CATALOG",
      "CREATE EXTERNAL LOCATION",
      "CREATE STORAGE CREDENTIAL",
      "CREATE SHARE",
      "CREATE RECIPIENT",
      "USE PROVIDER",
      "SET SHARE PERMISSION",
    ]
  }
}

# ── Workspace admin: nest dbx-workspace-admins into the built-in admins group ──
# Requires SCIM to have synced the Azure AD group into the workspace first.

data "databricks_group" "admins" {
  display_name = "admins"
}

data "databricks_group" "workspace_admins_synced" {
  display_name = azuread_group.databricks["workspace_admins"].display_name
  depends_on   = [azuread_group.databricks]
}

resource "databricks_group_member" "workspace_admins_nested" {
  group_id  = data.databricks_group.admins.id
  member_id = data.databricks_group.workspace_admins_synced.id
}
