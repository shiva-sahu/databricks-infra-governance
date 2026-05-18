# terraform/environments/prod/admins.tf

resource "databricks_user" "shiva" {
  user_name = "shiva-sahu@v4ctscoutlook.onmicrosoft.com"
}
