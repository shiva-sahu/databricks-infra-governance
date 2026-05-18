# terraform/environments/prod/admins.tf

resource "databricks_user" "shiva" {
  user_name = "shiva-sahu@v4ctscoutlook.onmicrosoft.com"
}

data "databricks_group" "admins" {
  display_name = "admins"
}

resource "databricks_group_member" "shiva_admin" {
  group_id  = data.databricks_group.admins.id
  member_id = databricks_user.shiva.id
}
