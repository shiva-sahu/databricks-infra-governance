# terraform/modules/rbac/variables.tf

variable "admin_groups" {
  description = "Databricks groups to assign the workspace admin role."
  type        = list(string)
  default     = []
}

variable "workspace_roles" {
  description = "Per-group workspace entitlements."
  type = list(object({
    group_name                = string
    can_create_clusters       = bool
    can_create_instance_pools = bool
    sql_access                = bool
  }))
  default = []
}

variable "secret_scope_acls" {
  description = "Cross-scope ACLs managed centrally via RBAC."
  type = list(object({
    scope      = string
    principal  = string
    permission = string
  }))
  default = []
}

variable "sql_warehouse_permissions" {
  description = "Map of SQL warehouse ID to list of group access control entries."
  type = map(list(object({
    group_name = string
    level      = string
  })))
  default = {}
}
