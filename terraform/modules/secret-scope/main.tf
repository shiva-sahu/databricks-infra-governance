# terraform/modules/secret-scope/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# Secret Scope Module
# Databricks secret scopes backed by Azure Key Vault.
# Naming convention: {env}_{purpose}
# Secrets are written to Key Vault externally (by the secrets pipeline).
# This module wires the scope and controls who can read from it.
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.35"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
  }
}

# ── Key Vault-backed Secret Scopes ────────────────────────────────────────────
resource "databricks_secret_scope" "scopes" {
  for_each = { for k, v in var.secret_scopes : k => v if v.key_vault_resource_id != "" }

  # Naming enforced: {env}_{purpose}
  name = "${var.environment}_${each.key}"

  # Azure Key Vault backend — secrets never live in Databricks natively
  keyvault_metadata {
    resource_id = each.value.key_vault_resource_id
    dns_name    = each.value.key_vault_dns_name
  }
}

# ── Scope ACLs ────────────────────────────────────────────────────────────────
# READ  — can fetch secrets (e.g. ETL service principals)
# WRITE — can add/update secrets (e.g. ops team)
# MANAGE — full control (admins only)
resource "databricks_secret_acl" "scope_acls" {
  for_each = {
    for acl in flatten([
      for scope_key, scope in var.secret_scopes : scope.key_vault_resource_id == "" ? [] : [
        for acl in scope.acls : {
          key        = "${scope_key}_${acl.principal}"
          scope_name = "${var.environment}_${scope_key}"
          principal  = acl.principal
          permission = acl.permission
        }
      ]
    ]) : acl.key => acl
  }

  scope      = each.value.scope_name
  principal  = each.value.principal
  permission = each.value.permission

  depends_on = [databricks_secret_scope.scopes]
}
