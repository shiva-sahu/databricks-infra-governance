# terraform/modules/rbac/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# RBAC Module
# Databricks groups, workspace assignments, and entitlements.
# Group membership is managed by the identity provider (Azure AD via SCIM).
# This module controls WHAT groups can DO in the workspace.
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.35"
    }
  }
}

# ── Groups ────────────────────────────────────────────────────────────────────
# Groups are synced from Azure AD via SCIM provisioning.
# We reference them here by name — we do not create or manage membership.
# Membership = Azure AD's job. Permissions = Terraform's job.

data "databricks_group" "groups" {
  for_each     = toset(local.all_group_names)
  display_name = each.value
}

locals {
  all_group_names = distinct(concat(
    [for r in var.workspace_roles : r.group_name],
    var.admin_groups
  ))
}

# ── Workspace Permissions ─────────────────────────────────────────────────────
resource "databricks_entitlements" "workspace_access" {
  for_each = {
    for r in var.workspace_roles : r.group_name => r
  }

  group_id                   = data.databricks_group.groups[each.key].id
  allow_cluster_create       = each.value.can_create_clusters
  allow_instance_pool_create = each.value.can_create_instance_pools
  databricks_sql_access      = each.value.sql_access
  workspace_access           = true
}

# ── Workspace Admins ──────────────────────────────────────────────────────────
# Admin group assignment. Minimise admin membership — principle of least privilege.
resource "databricks_group_role" "admins" {
  for_each = toset(var.admin_groups)

  group_id = data.databricks_group.groups[each.value].id
  role     = "roles/workspace.admin"
}

# ── Secret Scope ACLs ─────────────────────────────────────────────────────────
# Controlled here rather than in secret-scope module so RBAC is centralised.
resource "databricks_secret_acl" "scope_acls" {
  for_each = {
    for acl in var.secret_scope_acls :
    "${acl.scope}_${acl.principal}" => acl
  }

  scope      = each.value.scope
  principal  = each.value.principal
  permission = each.value.permission  # READ | WRITE | MANAGE
}

# ── SQL Warehouse Permissions ─────────────────────────────────────────────────
resource "databricks_permissions" "sql_warehouse" {
  for_each = var.sql_warehouse_permissions

  sql_endpoint_id = each.key

  dynamic "access_control" {
    for_each = each.value
    content {
      group_name       = access_control.value.group_name
      permission_level = access_control.value.level  # CAN_USE | CAN_MANAGE
    }
  }
}
