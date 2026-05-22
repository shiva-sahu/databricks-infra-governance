# terraform/modules/sql-warehouse/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# SQL Warehouse Module
# Two separate warehouses with distinct purposes and access controls:
#
#   {env}_analyst     — BI / ad-hoc queries. Accessed by analysts + engineers.
#                       Small size, short auto-stop, limited scale-out.
#
#   {env}_engineering — ETL validation, data quality checks, pipeline testing.
#                       Larger size, longer auto-stop, engineers only.
#
# Both warehouses:
#   - Type PRO (required for Unity Catalog row/column-level security)
#   - Photon enabled (vectorised execution, faster SQL)
#   - Auto-stop enforced (no zombie warehouses)
#   - Tagged for cost attribution
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.35"
    }
  }
}

# ── Analyst Warehouse ──────────────────────────────────────────────────────────
# Sized for interactive BI queries and dashboards.
# Analysts and engineers both get CAN_USE — engineers need it for query testing.
resource "databricks_sql_endpoint" "analyst" {
  name             = "${var.environment}_analyst"
  cluster_size     = var.analyst_cluster_size
  max_num_clusters = var.analyst_max_clusters
  auto_stop_mins   = var.analyst_auto_stop_mins

  warehouse_type = "Serverless"
  enable_photon  = true

  channel {
    name = "CHANNEL_NAME_CURRENT"
  }

  tags {
    custom_tags {
      key   = "environment"
      value = var.environment
    }
    custom_tags {
      key   = "purpose"
      value = "analyst"
    }
    custom_tags {
      key   = "cost_centre"
      value = var.cost_centre
    }
    custom_tags {
      key   = "managed_by"
      value = "terraform"
    }
  }
}

# ── Engineering Warehouse ──────────────────────────────────────────────────────
# Sized for ETL validation, data quality checks, and pipeline testing.
# Engineers only — analysts do not run pipeline workloads.
resource "databricks_sql_endpoint" "engineer" {
  name             = "${var.environment}_engineering"
  cluster_size     = var.engineer_cluster_size
  max_num_clusters = var.engineer_max_clusters
  auto_stop_mins   = var.engineer_auto_stop_mins

  warehouse_type = "PRO"
  enable_photon  = true

  channel {
    name = "CHANNEL_NAME_CURRENT"
  }

  tags {
    custom_tags {
      key   = "environment"
      value = var.environment
    }
    custom_tags {
      key   = "purpose"
      value = "engineering"
    }
    custom_tags {
      key   = "cost_centre"
      value = var.cost_centre
    }
    custom_tags {
      key   = "managed_by"
      value = "terraform"
    }
  }
}

# ── Warehouse Permissions ──────────────────────────────────────────────────────
# CAN_USE  — run queries against the warehouse
# CAN_MANAGE — modify warehouse configuration (reserved for admins via Terraform)

resource "databricks_permissions" "analyst_warehouse" {
  sql_endpoint_id = databricks_sql_endpoint.analyst.id

  dynamic "access_control" {
    for_each = var.analyst_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}

resource "databricks_permissions" "engineer_warehouse" {
  sql_endpoint_id = databricks_sql_endpoint.engineer.id

  dynamic "access_control" {
    for_each = var.engineer_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}
