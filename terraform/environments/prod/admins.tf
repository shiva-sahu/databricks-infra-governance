# terraform/environments/prod/admins.tf
# ─────────────────────────────────────────────────────────────────────────────
# Admin user assignments for the prod workspace.
# Users are added to their respective Azure AD admin groups defined in groups.tf.
# ─────────────────────────────────────────────────────────────────────────────

# ── Look up Azure AD users ────────────────────────────────────────────────────

data "azuread_user" "shiva" {
  user_principal_name = "shiva-sahu@v4ctscoutlook.onmicrosoft.com"
}

data "azuread_user" "jahnavi" {
  user_principal_name = "jahnavi.b.k@v4c.ai"
}

# ── Group membership ──────────────────────────────────────────────────────────

resource "azuread_group_member" "shiva_metastore_admin" {
  group_object_id  = azuread_group.databricks["metastore_admins"].object_id
  member_object_id = data.azuread_user.shiva.object_id
}

resource "azuread_group_member" "jahnavi_workspace_admin" {
  group_object_id  = azuread_group.databricks["workspace_admins"].object_id
  member_object_id = data.azuread_user.jahnavi.object_id
}

# ── Databricks: metastore grants for the admin group ─────────────────────────
# Applied once the group is synced to Databricks via SCIM.

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

# ── Databricks: workspace admin group ─────────────────────────────────────────
# Adds the workspace_admins Azure AD group to the Databricks built-in admins group
# once SCIM sync brings it into the workspace.

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
