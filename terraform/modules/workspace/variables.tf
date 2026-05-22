# terraform/modules/workspace/variables.tf

variable "prefix" {
  description = "Organisation prefix for all resource names. e.g. 'gcw'"
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,8}$", var.prefix))
    error_message = "Prefix must be 2-9 lowercase alphanumeric chars or hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "Deployment target: dev | staging | prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "location" {
  description = "Azure region. e.g. 'eastus2'"
  type        = string
  default     = "eastus2"
}

variable "sku" {
  description = "Databricks SKU. Must be 'premium' for Unity Catalog."
  type        = string
  default     = "premium"
  validation {
    condition     = var.sku == "premium"
    error_message = "SKU must be 'premium' — Unity Catalog requires premium tier."
  }
}

variable "vnet_cidr" {
  description = "CIDR block for the Databricks VNet."
  type        = string
  default     = "10.10.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the public (host) subnet."
  type        = string
  default     = "10.10.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR for the private (container) subnet."
  type        = string
  default     = "10.10.2.0/24"
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID for audit log streaming. Leave empty to skip diagnostic settings."
  type        = string
  default     = ""
}

variable "team" {
  description = "Owning team name. Used in tags and naming."
  type        = string
}

variable "cost_centre" {
  description = "Cost centre code for billing attribution."
  type        = string
}

variable "project" {
  description = "Project or application name for governance attribution."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,50}$", var.project))
    error_message = "Project must be lowercase alphanumeric with hyphens, starting with a letter."
  }
}

variable "owner" {
  description = "Owning team contact (email or alias) for governance accountability."
  type        = string
}

variable "allowed_ip_ranges" {
  description = "CIDR ranges allowed to access the Databricks workspace. Empty list means no IP restriction."
  type        = list(string)
  default     = []
}

variable "enforce_workspace_conf" {
  description = "Apply workspace-level governance settings (notebook export restriction, etc.)."
  type        = bool
  default     = true
}

variable "additional_tags" {
  description = "Additional tags to merge with common tags."
  type        = map(string)
  default     = {}
}
