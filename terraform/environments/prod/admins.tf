# terraform/environments/prod/admins.tf

resource "databricks_grants" "metastore_admin" {
  metastore = var.metastore_id

  grant {
    principal = local.groups["metastore_admins"]
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
