# terraform/modules/unity-catalog/outputs.tf

output "catalog_names" {
  description = "Map of catalog key → actual Databricks catalog name"
  value       = { for k, v in databricks_catalog.catalogs : k => v.name }
}

output "schema_names" {
  description = "Map of schema key → full schema path (catalog.schema)"
  value = {
    for k, v in databricks_schema.schemas :
    k => "${v.catalog_name}.${v.name}"
  }
}

output "external_location_name" {
  description = "Name of the external location, or empty string if not created"
  value       = var.access_connector_id != "" ? databricks_external_location.main[0].name : ""
}
