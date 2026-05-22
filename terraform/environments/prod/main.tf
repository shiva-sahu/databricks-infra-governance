# terraform/environments/prod/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# Prod Environment
# Composes all modules into a complete Databricks platform.
# This file is the source of truth for what exists in prod.
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.35"
    }
  }

  # Remote state: Azure Blob Storage
  # Never use local state. State = the record of what exists.
  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "v4cdev"
    container_name       = "tfstate"
    key                  = "databricks-governance/prod/terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
  # Credentials injected via environment variables:
  # ARM_CLIENT_ID, ARM_CLIENT_SECRET, ARM_SUBSCRIPTION_ID, ARM_TENANT_ID
}

provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

# ── Workspace ─────────────────────────────────────────────────────────────────
module "workspace" {
  source = "../../modules/workspace"

  prefix      = "demo"
  environment = "prod"
  location    = "eastus2"
  team        = "platform"
  cost_centre = "CC-1001"
  project     = "databricks-governance-demo"
  owner       = "platform-team@v4c.ai"

  vnet_cidr           = "10.20.0.0/16"
  public_subnet_cidr  = "10.20.1.0/24"
  private_subnet_cidr = "10.20.2.0/24"

  log_analytics_workspace_id = var.log_analytics_workspace_id

  # Prod: restrict access to corporate network CIDRs
  allowed_ip_ranges      = var.corporate_ip_ranges
  enforce_workspace_conf = true

  additional_tags = {
    created_by = "terraform"
  }
}

# ── Unity Catalog ─────────────────────────────────────────────────────────────
module "unity_catalog" {
  source = "../../modules/unity-catalog"

  metastore_id         = var.metastore_id
  workspace_numeric_id = var.workspace_numeric_id
  environment          = "prod"
  team                 = "platform"
  access_connector_id  = var.access_connector_id
  adls_storage_account = var.adls_storage_account
  adls_container       = "unitycatalog-prod"

  catalogs = {
    ecommerce = {
      team                = "ecommerce"
      domain              = "ecommerce"
      comment             = "E-commerce domain: orders, products, customers. Production environment."
      owner_group         = "lll-data-engineers"
      cost_centre         = "CC-1002"
      data_classification = "internal"
      project             = "databricks-governance-demo"
      owner_contact       = "ecommerce-team@v4c.ai"
      grants = [
        {
          principal  = "lll-data-engineers"
          privileges = ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "MODIFY"]
        },
        {
          principal  = "lll-data-analysts"
          privileges = ["USE_CATALOG", "SELECT"]
        }
      ]
      schema_grants = {
        bronze = [
          { principal = "lll-data-engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] }
        ]
        silver = [
          { principal = "lll-data-engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
          { principal = "lll-data-analysts",  privileges = ["USE_SCHEMA", "SELECT"] }
        ]
        gold = [
          { principal = "lll-data-engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
          { principal = "lll-data-analysts",  privileges = ["USE_SCHEMA", "SELECT"] }
        ]
      }
    }

    finance = {
      team                = "finance"
      domain              = "finance"
      comment             = "Finance domain: GL, AP, AR, FX. Production environment."
      owner_group         = "lll-data-engineers"
      cost_centre         = "CC-1003"
      data_classification = "confidential"
      project             = "databricks-governance-demo"
      owner_contact       = "finance-team@v4c.ai"
      grants = [
        {
          principal  = "lll-data-engineers"
          privileges = ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "MODIFY"]
        },
        {
          principal  = "lll-data-analysts"
          privileges = ["USE_CATALOG", "SELECT"]
        }
      ]
      schema_grants = {
        bronze = [
          { principal = "lll-data-engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] }
        ]
        silver = [
          { principal = "lll-data-engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
          { principal = "lll-data-analysts",  privileges = ["USE_SCHEMA", "SELECT"] }
        ]
        gold = [
          { principal = "lll-data-engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
          { principal = "lll-data-analysts",  privileges = ["USE_SCHEMA", "SELECT"] }
        ]
      }
    }
  }

  external_location_grants = [
    { principal = "lll-data-engineers", privileges = ["READ_FILES"] }
  ]
}

# ── Cluster Policies ──────────────────────────────────────────────────────────
module "cluster_policies" {
  source = "../../modules/cluster-policy"

  environment = "prod"

  approved_node_types = [
    "Standard_DS3_v2",
    "Standard_DS4_v2",
    "Standard_E8ds_v5"
  ]

  interactive_policy_groups = ["lll-data-analysts", "lll-data-engineers"]
  job_policy_groups         = ["lll-data-engineers"]
  ml_policy_groups          = ["lll-data-engineers"]
  high_memory_policy_groups = ["lll-data-engineers"]
  single_user_policy_groups = ["lll-data-engineers", "lll-data-analysts"]
}

# ── SQL Warehouses ────────────────────────────────────────────────────────────
module "sql_warehouses" {
  source = "../../modules/sql-warehouse"

  environment = "prod"
  cost_centre = "CC-1001"

  # Analyst warehouse: BI queries, dashboards, ad-hoc exploration
  analyst_cluster_size   = "2X-Small"
  analyst_max_clusters   = 1
  analyst_auto_stop_mins = 10
  analyst_groups         = ["lll-data-analysts", "lll-data-engineers"]

  # Engineering warehouse: ETL validation, data quality, pipeline testing
  engineer_cluster_size   = "2X-Small"
  engineer_max_clusters   = 1
  engineer_auto_stop_mins = 20
  engineer_groups         = ["lll-data-engineers"]
}

# ── Secret Scopes ─────────────────────────────────────────────────────────────
module "secret_scopes" {
  source = "../../modules/secret-scope"

  environment = "prod"

  secret_scopes = {
    api_keys = {
      key_vault_resource_id = var.key_vault_resource_id
      key_vault_dns_name    = var.key_vault_dns_name
      acls = [
        { principal = "lll-data-engineers", permission = "READ" },
        { principal = "admins",             permission = "MANAGE" }
      ]
    }
  }
}
