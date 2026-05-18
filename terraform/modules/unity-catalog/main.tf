# terraform/modules/unity-catalog/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# Unity Catalog Module
# Metastore attachment, external locations, catalogs, schemas, and grants.
# Naming convention enforced: {env}_{team}_{domain} for catalogs
#                              {domain}_{layer} for schemas (bronze/silver/gold)
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

# ── Metastore Assignment ──────────────────────────────────────────────────────
# The metastore is created ONCE at account level and assigned to workspaces.
# It is NOT recreated per environment — it's shared and managed centrally.
resource "databricks_metastore_assignment" "this" {
  count = var.metastore_id != "" && var.workspace_numeric_id != "" ? 1 : 0

  metastore_id = var.metastore_id
  workspace_id = tonumber(var.workspace_numeric_id)
}

# ── External Location (ADLS Gen2) ─────────────────────────────────────────────
# All Unity Catalog data lives in managed external location.
# Credentials are managed by Terraform — never manually created.
resource "databricks_storage_credential" "adls" {
  name = "${var.environment}_${var.team}_storage_credential"

  azure_managed_identity {
    access_connector_id = var.access_connector_id
  }

  comment = "Managed by Terraform. Do not modify manually. Repo: databricks-governance-demo"

  depends_on = [databricks_metastore_assignment.this]

  lifecycle {
    prevent_destroy = true
  }
}

resource "databricks_external_location" "main" {
  name            = "${var.environment}_${var.team}_external_location"
  url             = "abfss://${var.adls_container}@${var.adls_storage_account}.dfs.core.windows.net/"
  credential_name = databricks_storage_credential.adls.name
  comment         = "Primary data lake location. Managed by Terraform."

  depends_on = [databricks_metastore_assignment.this]

  lifecycle {
    prevent_destroy = true
  }
}

# ── Catalogs ──────────────────────────────────────────────────────────────────
# Naming: {env}_{team}_{domain}
# Each catalog is a governance boundary. One per domain.
resource "databricks_catalog" "catalogs" {
  for_each = var.catalogs

  # Enforce naming convention via Terraform
  name         = "${var.environment}_${each.value.team}_${each.value.domain}"
  metastore_id = var.metastore_id
  comment      = each.value.comment
  owner        = each.value.owner_group  # Always a group. Never an individual.

  storage_root = "${databricks_external_location.main.url}${each.key}/"

  depends_on = [databricks_metastore_assignment.this]

  properties = {
    environment  = var.environment
    team         = each.value.team
    domain       = each.value.domain
    cost_centre  = each.value.cost_centre
    managed_by   = "terraform"
  }

  lifecycle {
    prevent_destroy = true
    # If name changes, the catalog must be explicitly targeted for replacement
    # This prevents accidental data loss from a rename
  }
}

# ── Schemas (Medallion Architecture) ──────────────────────────────────────────
# Naming: {domain}_{layer}
# Layers: bronze (raw), silver (cleansed), gold (business-ready)
resource "databricks_schema" "schemas" {
  for_each = {
    for item in flatten([
      for catalog_key, catalog in var.catalogs : [
        for layer in ["bronze", "silver", "gold"] : {
          key         = "${catalog_key}_${layer}"
          catalog_key = catalog_key
          catalog     = catalog
          layer       = layer
        }
      ]
    ]) : item.key => item
  }

  catalog_name = databricks_catalog.catalogs[each.value.catalog_key].name
  name         = "${each.value.catalog.domain}_${each.value.layer}"
  comment      = "${title(each.value.layer)} layer for ${each.value.catalog.domain} domain. Managed by Terraform."
  owner        = each.value.catalog.owner_group

  properties = {
    layer        = each.value.layer
    domain       = each.value.catalog.domain
    managed_by   = "terraform"
  }
}

# ── Catalog Grants ────────────────────────────────────────────────────────────
# CRITICAL GOVERNANCE RULES (enforced by tests/governance/test_permissions.py):
# 1. No ALL PRIVILEGES to individuals — groups only
# 2. prod catalogs: dev_team gets READ only, never MODIFY
# 3. service principals get only what they need for their job
# 4. Every grant is explicit and documented

resource "databricks_grants" "catalog_grants" {
  for_each = var.catalogs

  catalog = databricks_catalog.catalogs[each.key].name

  dynamic "grant" {
    for_each = each.value.grants
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}

resource "databricks_grants" "schema_grants" {
  for_each = {
    for item in flatten([
      for catalog_key, catalog in var.catalogs : [
        for layer in ["bronze", "silver", "gold"] : {
          key         = "${catalog_key}_${layer}"
          catalog_key = catalog_key
          layer       = layer
          grants      = lookup(catalog.schema_grants, layer, [])
        }
      ]
    ]) : item.key => item
    if length(item.grants) > 0
  }

  schema = "${databricks_catalog.catalogs[each.value.catalog_key].name}.${databricks_schema.schemas[each.key].name}"

  dynamic "grant" {
    for_each = each.value.grants
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}

# ── External Location Grants ──────────────────────────────────────────────────
resource "databricks_grants" "external_location" {
  external_location = databricks_external_location.main.name

  dynamic "grant" {
    for_each = var.external_location_grants
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}
