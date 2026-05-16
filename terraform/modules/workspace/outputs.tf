# terraform/modules/workspace/outputs.tf

output "workspace_id" {
  description = "Databricks workspace resource ID."
  value       = azurerm_databricks_workspace.main.id
}

output "workspace_url" {
  description = "Databricks workspace URL."
  value       = "https://${azurerm_databricks_workspace.main.workspace_url}"
}

output "workspace_name" {
  description = "Databricks workspace name."
  value       = azurerm_databricks_workspace.main.name
}

output "resource_group_name" {
  description = "Resource group containing the workspace."
  value       = azurerm_resource_group.databricks.name
}

output "vnet_id" {
  description = "VNet ID for reference by other modules."
  value       = azurerm_virtual_network.databricks.id
}
