# terraform/environments/prod/variables.tf

variable "databricks_host" {
  description = "Databricks workspace URL. Injected via DATABRICKS_HOST env var in CI."
  type        = string
  sensitive   = true
}

variable "databricks_token" {
  description = "Databricks PAT or SP token. Injected via DATABRICKS_TOKEN in CI."
  type        = string
  sensitive   = true
}

variable "metastore_id" {
  description = "Unity Catalog metastore ID."
  type        = string
  default     = ""
}

variable "workspace_numeric_id" {
  description = "Numeric workspace ID for metastore assignment."
  type        = string
  default     = ""
}

variable "access_connector_id" {
  description = "Azure Access Connector resource ID."
  type        = string
}

variable "adls_storage_account" {
  description = "ADLS Gen2 storage account name."
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for audit streaming."
  type        = string
}

variable "key_vault_resource_id" {
  description = "Azure Key Vault resource ID for secret scopes."
  type        = string
}

variable "key_vault_dns_name" {
  description = "Azure Key Vault DNS name. e.g. https://myvault.vault.azure.net/"
  type        = string
}
