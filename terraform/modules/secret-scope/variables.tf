# terraform/modules/secret-scope/variables.tf

variable "environment" {
  description = "Deployment environment. Used as a prefix in scope names."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "secret_scopes" {
  description = "Map of secret scopes to create, keyed by purpose name."
  type = map(object({
    key_vault_resource_id = string
    key_vault_dns_name    = string
    acls = list(object({
      principal  = string
      permission = string
    }))
  }))
  default = {}
}
