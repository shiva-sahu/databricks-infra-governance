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

  vnet_cidr           = "10.20.0.0/16"
  public_subnet_cidr  = "10.20.1.0/24"
  private_subnet_cidr = "10.20.2.0/24"

  log_analytics_workspace_id = var.log_analytics_workspace_id

  additional_tags = {
    project    = "databricks-governance-demo"
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

  # Each catalog = a governed data domain
  catalogs = {
    ecommerce = {
      team        = "ecommerce"
      domain      = "ecommerce"
      comment     = "E-commerce domain: orders, products, customers. Production environment."
      owner_group = "ecommerce_data_engineers"
      cost_centre = "CC-1002"
      grants = [
        {
          principal  = "ecommerce_data_engineers"
          privileges = ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "MODIFY"]
        },
        {
          principal  = "data_analysts"
          privileges = ["USE_CATALOG", "SELECT"]
        }
      ]
      schema_grants = {
        bronze = [
          {
            principal  = "ecommerce_data_engineers"
            privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"]
          }
        ]
        silver = [
          {
            principal  = "ecommerce_data_engineers"
            privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"]
          },
          {
            principal  = "data_analysts"
            privileges = ["USE_SCHEMA", "SELECT"]
          }
        ]
        gold = [
          {
            principal  = "ecommerce_data_engineers"
            privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"]
          },
          {
            principal  = "data_analysts"
            privileges = ["USE_SCHEMA", "SELECT"]
          },
          {
            principal  = "data_scientists"
            privileges = ["USE_SCHEMA", "SELECT"]
          }
        ]
      }
    }

    finance = {
      team        = "finance"
      domain      = "finance"
      comment     = "Finance domain: GL, AP, AR, FX. Production environment."
      owner_group = "finance_data_engineers"
      cost_centre = "CC-1003"
      grants = [
        {
          principal  = "finance_data_engineers"
          privileges = ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "MODIFY"]
        },
        {
          principal  = "finance_analysts"
          privileges = ["USE_CATALOG", "SELECT"]
        }
      ]
      schema_grants = {
        bronze = [
          { principal = "finance_data_engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] }
        ]
        silver = [
          { principal = "finance_data_engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
          { principal = "finance_analysts", privileges = ["USE_SCHEMA", "SELECT"] }
        ]
        gold = [
          { principal = "finance_data_engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
          { principal = "finance_analysts", privileges = ["USE_SCHEMA", "SELECT"] }
        ]
      }
    }
  }

  external_location_grants = [
    { principal = "ecommerce_data_engineers", privileges = ["READ_FILES"] },
    { principal = "finance_data_engineers", privileges = ["READ_FILES"] }
  ]
}

# ── Cluster Policies ──────────────────────────────────────────────────────────
module "cluster_policies" {
  source = "../../modules/cluster-policy"

  environment = "prod"

  # Prod: locked to cost-controlled, approved node types only
  approved_node_types = [
    "Standard_DS3_v2",
    "Standard_DS4_v2",
    "Standard_E8ds_v5"
  ]

  interactive_policy_groups = ["data_analysts", "data_engineers", "data_scientists"]
  job_policy_groups         = ["data_engineers"]
}

# ── Secret Scopes ─────────────────────────────────────────────────────────────
module "secret_scopes" {
  source = "../../modules/secret-scope"

  environment = "prod"

  secret_scopes = {
    postgres = {
      key_vault_resource_id = var.key_vault_resource_id
      key_vault_dns_name    = var.key_vault_dns_name
      acls = [
        { principal = "data_engineers", permission = "READ" },
        { principal = "admins", permission = "MANAGE" }
      ]
    }
    api_keys = {
      key_vault_resource_id = var.key_vault_resource_id
      key_vault_dns_name    = var.key_vault_dns_name
      acls = [
        { principal = "data_engineers", permission = "READ" },
        { principal = "admins", permission = "MANAGE" }
      ]
    }
  }
}

# ── RBAC ──────────────────────────────────────────────────────────────────────
module "rbac" {
  source = "../../modules/rbac"

  admin_groups = ["dbx-admins", "platform_engineers"]

  workspace_roles = [
    { group_name = "data_engineers", can_create_clusters = true, can_create_instance_pools = false, sql_access = true },
    { group_name = "data_analysts", can_create_clusters = false, can_create_instance_pools = false, sql_access = true },
    { group_name = "data_scientists", can_create_clusters = true, can_create_instance_pools = false, sql_access = true },
    { group_name = "ecommerce_data_engineers", can_create_clusters = true, can_create_instance_pools = false, sql_access = true },
    { group_name = "finance_data_engineers", can_create_clusters = true, can_create_instance_pools = false, sql_access = true },
    { group_name = "finance_analysts", can_create_clusters = false, can_create_instance_pools = false, sql_access = true },
  ]

  secret_scope_acls         = [] # Managed per-scope in secret_scopes module
  sql_warehouse_permissions = {} # Add warehouse IDs once created
}
