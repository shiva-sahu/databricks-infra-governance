# terraform/environments/prod/admins.tf
# ─────────────────────────────────────────────────────────────────────────────
# Admin assignments for the prod workspace.
# ─────────────────────────────────────────────────────────────────────────────

# ── Users ─────────────────────────────────────────────────────────────────────

resource "databricks_user" "shiva" {
  user_name = "shiva-sahu@v4ctscoutlook.onmicrosoft.com"
}

resource "databricks_user" "jahnavi" {
  user_name = "jahnavi.b.k@v4c.ai"
}

# ── Metastore Admin — shiva ───────────────────────────────────────────────────
# Grants full metastore-level administrative privileges.

resource "databricks_grants" "metastore_admin" {
  metastore = var.metastore_id

  grant {
    principal = databricks_user.shiva.user_name
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

# ── Workspace Admin — jahnavi ─────────────────────────────────────────────────
# Adds jahnavi to the built-in workspace admins group.

data "databricks_group" "admins" {
  display_name = "admins"
}

resource "databricks_group_member" "jahnavi_admin" {
  group_id  = data.databricks_group.admins.id
  member_id = databricks_user.jahnavi.id
}
