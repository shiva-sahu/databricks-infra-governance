# terraform/modules/unity-catalog/variables.tf

variable "metastore_id" {
  description = "Databricks Unity Catalog metastore ID. Created once at account level."
  type        = string
}

variable "workspace_numeric_id" {
  description = "Numeric workspace ID for metastore assignment."
  type        = string
}

variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "team" {
  description = "Team identifier used in catalog naming."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{1,20}$", var.team))
    error_message = "Team must be lowercase alphanumeric with underscores."
  }
}

variable "access_connector_id" {
  description = "Azure Access Connector resource ID for ADLS storage credentials."
  type        = string
}

variable "adls_storage_account" {
  description = "Azure Data Lake Storage Gen2 account name."
  type        = string
}

variable "adls_container" {
  description = "ADLS container name for Unity Catalog managed storage."
  type        = string
}

variable "catalogs" {
  description = <<-EOT
    Map of catalog configurations.
    Key = catalog logical name (used internally).
    
    Each catalog entry:
    - team:          Team owning this catalog
    - domain:        Business domain (e.g. "ecommerce", "finance")
    - comment:       Human-readable description
    - owner_group:   Databricks group that owns the catalog (NEVER an individual)
    - cost_centre:   Cost attribution code
    - grants:        List of { principal, privileges[] } — groups only
    - schema_grants: Map of layer → list of { principal, privileges[] }
  EOT
  type = map(object({
    team        = string
    domain      = string
    comment     = string
    owner_group = string
    cost_centre = string
    grants = list(object({
      principal  = string
      privileges = list(string)
    }))
    schema_grants = map(list(object({
      principal  = string
      privileges = list(string)
    })))
  }))

  validation {
    condition = alltrue([
      for k, v in var.catalogs : can(regex("^[a-z][a-z0-9_]{1,20}$", v.domain))
    ])
    error_message = "All catalog domain values must be lowercase alphanumeric with underscores."
  }

  validation {
    condition = alltrue(flatten([
      for k, v in var.catalogs : [
        for g in v.grants : !contains(g.privileges, "ALL PRIVILEGES")
      ]
    ]))
    error_message = "ALL PRIVILEGES is not allowed in catalog grants. Use explicit privilege lists."
  }
}

variable "external_location_grants" {
  description = "Grants for the primary external location."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}
