# terraform/modules/workspace/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# Azure Databricks Workspace Module
# Creates the workspace, VNet injection, diagnostic settings, and tags.
# Everything a workspace needs at birth — declarative, reproducible.
# ─────────────────────────────────────────────────────────────────────────────

terraform {
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
}

# ── Resource Group ────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "databricks" {
  name     = "${var.prefix}-${var.environment}-databricks-rg"
  location = var.location
  tags     = local.common_tags
}

# ── Virtual Network ───────────────────────────────────────────────────────────
resource "azurerm_virtual_network" "databricks" {
  name                = "${var.prefix}-${var.environment}-dbx-vnet"
  resource_group_name = azurerm_resource_group.databricks.name
  location            = azurerm_resource_group.databricks.location
  address_space       = [var.vnet_cidr]
  tags                = local.common_tags
}

resource "azurerm_subnet" "public" {
  name                 = "databricks-public"
  resource_group_name  = azurerm_resource_group.databricks.name
  virtual_network_name = azurerm_virtual_network.databricks.name
  address_prefixes     = [var.public_subnet_cidr]

  delegation {
    name = "databricks-delegation"
    service_delegation {
      name = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action",
      ]
    }
  }
}

resource "azurerm_subnet" "private" {
  name                 = "databricks-private"
  resource_group_name  = azurerm_resource_group.databricks.name
  virtual_network_name = azurerm_virtual_network.databricks.name
  address_prefixes     = [var.private_subnet_cidr]

  delegation {
    name = "databricks-delegation"
    service_delegation {
      name = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action",
      ]
    }
  }
}

# NSG required for VNet injection
resource "azurerm_network_security_group" "databricks" {
  name                = "${var.prefix}-${var.environment}-dbx-nsg"
  resource_group_name = azurerm_resource_group.databricks.name
  location            = azurerm_resource_group.databricks.location
  tags                = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "public" {
  subnet_id                 = azurerm_subnet.public.id
  network_security_group_id = azurerm_network_security_group.databricks.id
}

resource "azurerm_subnet_network_security_group_association" "private" {
  subnet_id                 = azurerm_subnet.private.id
  network_security_group_id = azurerm_network_security_group.databricks.id
}

# ── Databricks Workspace ──────────────────────────────────────────────────────
resource "azurerm_databricks_workspace" "main" {
  name                = "${var.prefix}-${var.environment}-workspace"
  resource_group_name = azurerm_resource_group.databricks.name
  location            = azurerm_resource_group.databricks.location
  sku                 = var.sku  # "premium" required for Unity Catalog

  # VNet injection — no public IPs on workers
  custom_parameters {
    no_public_ip                                         = true
    virtual_network_id                                   = azurerm_virtual_network.databricks.id
    public_subnet_name                                   = azurerm_subnet.public.name
    private_subnet_name                                  = azurerm_subnet.private.name
    public_subnet_network_security_group_association_id  = azurerm_subnet_network_security_group_association.public.id
    private_subnet_network_security_group_association_id = azurerm_subnet_network_security_group_association.private.id
  }

  # Governance: workspace-level settings
  managed_resource_group_name = "${var.prefix}-${var.environment}-databricks-managed-rg"

  tags = local.common_tags

  timeouts {
    create = "60m"
    update = "60m"
  }

  lifecycle {
    # prevent_destroy omitted intentionally: the workspace is compute infrastructure.
    # Data lives in Unity Catalog (ADLS-backed) and survives workspace recreation.
    # Re-enable once the workspace is stable and has production workloads.
    ignore_changes = [tags["LastModified"]]
  }
}

# ── Diagnostic Settings (Audit Logs) ─────────────────────────────────────────
resource "azurerm_monitor_diagnostic_setting" "databricks" {
  count = var.log_analytics_workspace_id != "" ? 1 : 0

  name                       = "${var.prefix}-${var.environment}-dbx-diag"
  target_resource_id         = azurerm_databricks_workspace.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log { category = "dbfs" }
  enabled_log { category = "clusters" }
  enabled_log { category = "accounts" }
  enabled_log { category = "jobs" }
  enabled_log { category = "notebook" }
  enabled_log { category = "secrets" }
  enabled_log { category = "sqlPermissions" }
  enabled_log { category = "instancePools" }
  enabled_log { category = "sqlAnalyticsOperations" }
  enabled_log { category = "genie" }
  enabled_log { category = "globalInitScripts" }
  enabled_log { category = "iamRole" }
  enabled_log { category = "mlflowExperiment" }
  enabled_log { category = "featureStore" }
  enabled_log { category = "RemoteHistoryService" }
  enabled_log { category = "unityCatalog" }
}

# ── Workspace-Level Governance Configuration ──────────────────────────────────
resource "databricks_workspace_conf" "governance" {
  count = var.enforce_workspace_conf ? 1 : 0

  custom_config = {
    # Block notebook result downloads — data stays in the platform
    "enableExportNotebook"               = "false"
    # Enforce Unity Catalog as the default namespace
    "defaultNamespaceName"               = var.environment
    # Service principals can be granted workspace entitlements via Terraform
    "enableServicePrincipalEntitlements" = "true"
  }
}

# ── IP Access List ─────────────────────────────────────────────────────────────
resource "databricks_ip_access_list" "allowed" {
  count = length(var.allowed_ip_ranges) > 0 ? 1 : 0

  label        = "${var.environment}-corporate-network"
  list_type    = "ALLOW"
  ip_addresses = var.allowed_ip_ranges

  depends_on = [azurerm_databricks_workspace.main]
}

# ── Local Values ──────────────────────────────────────────────────────────────
locals {
  common_tags = merge(var.additional_tags, {
    environment  = var.environment
    team         = var.team
    cost_centre  = var.cost_centre
    project      = var.project
    owner        = var.owner
    managed_by   = "terraform"
    repo         = "databricks-governance-demo"
    last_updated = timestamp()
  })
}
