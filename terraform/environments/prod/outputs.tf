# terraform/environments/prod/outputs.tf

output "catalog_names" {
  description = "Databricks catalog names created in this environment"
  value       = module.unity_catalog.catalog_names
}

output "schema_names" {
  description = "Databricks schema names (catalog.schema) created in this environment"
  value       = module.unity_catalog.schema_names
}

output "external_location_name" {
  description = "External location name for the ADLS Gen2 data lake"
  value       = module.unity_catalog.external_location_name
}

output "workspace_id" {
  description = "Azure resource ID of the Databricks workspace"
  value       = module.workspace.workspace_id
}

output "workspace_url" {
  description = "URL of the Databricks workspace"
  value       = module.workspace.workspace_url
}
