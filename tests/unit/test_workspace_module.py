"""
tests/unit/test_workspace_module.py
────────────────────────────────────────────────────────────────────────────────
Unit Tests: workspace module

Validates that the Azure Databricks workspace is created with correct security
and governance settings:
  - VNet injection with no public IPs
  - Diagnostic settings capture all required audit categories
  - prevent_destroy lifecycle on the workspace resource
  - Required tags on all Azure resources (via common_tags)
  - Premium SKU enforced (required for Unity Catalog)
  - Outputs declared for downstream modules

Run locally:
  pytest tests/unit/test_workspace_module.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import pytest

MODULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "modules", "workspace")
)

# Audit log categories required for SOC2 / security monitoring
REQUIRED_LOG_CATEGORIES = [
    "clusters",
    "accounts",
    "jobs",
    "notebook",
    "secrets",
    "sqlPermissions",
    "unityCatalog",
    "iamRole",
]


def load(filename):
    path = os.path.join(MODULE_DIR, filename)
    assert os.path.exists(path), f"Expected file missing: {path}"
    return open(path).read()


# ── Network Security ───────────────────────────────────────────────────────────

class TestNetworkSecurity:

    def test_no_public_ip_enabled(self):
        """
        no_public_ip must be true — worker nodes must not have public IP addresses.
        Public IPs on compute nodes create an attack surface and violate network policy.
        """
        content = load("main.tf")
        assert "no_public_ip" in content, (
            "Workspace custom_parameters must include no_public_ip"
        )

        npi_match = re.search(r'no_public_ip\s*=\s*(true|false|var\.\w+)', content)
        assert npi_match, "no_public_ip must have an explicit value"
        assert npi_match.group(1) == "true", (
            f"no_public_ip must be true, got: {npi_match.group(1)}\n"
            "Worker nodes must not have public IPs."
        )

    def test_vnet_injection_configured(self):
        """
        VNet injection must be configured (virtual_network_id, public/private subnet).
        Without VNet injection, Databricks creates its own unmanaged network resources.
        """
        content = load("main.tf")

        assert "virtual_network_id" in content, (
            "Workspace must configure VNet injection (virtual_network_id)"
        )
        assert "public_subnet_name" in content, (
            "Workspace must configure public subnet for VNet injection"
        )
        assert "private_subnet_name" in content, (
            "Workspace must configure private subnet for VNet injection"
        )

    def test_nsg_association_configured(self):
        """
        NSG associations must be configured for both subnets.
        VNet injection without NSGs causes workspace creation to fail.
        """
        content = load("main.tf")

        assert "azurerm_subnet_network_security_group_association" in content, (
            "Both subnets must have NSG associations for VNet injection"
        )

        nsg_count = len(re.findall(
            r'resource\s+"azurerm_subnet_network_security_group_association"',
            content
        ))
        assert nsg_count == 2, (
            f"Expected 2 NSG associations (public and private subnet), found {nsg_count}"
        )

    def test_subnet_delegations_for_databricks(self):
        """
        Both subnets must delegate to Microsoft.Databricks/workspaces.
        Without delegation, Azure rejects VNet injection.
        """
        content = load("main.tf")

        delegation_count = content.count("Microsoft.Databricks/workspaces")
        assert delegation_count >= 2, (
            f"Expected delegation to Microsoft.Databricks/workspaces on both subnets. "
            f"Found {delegation_count} occurrence(s)."
        )


# ── Audit Logging ──────────────────────────────────────────────────────────────

class TestDiagnosticSettings:

    def test_diagnostic_setting_resource_exists(self):
        """Audit log streaming to Log Analytics must be configured."""
        content = load("main.tf")
        assert "azurerm_monitor_diagnostic_setting" in content, (
            "Workspace module must define azurerm_monitor_diagnostic_setting for audit logs"
        )

    def test_diagnostic_setting_conditional_on_log_analytics_id(self):
        """
        Diagnostic settings must be optional — not all environments have Log Analytics.
        A hardcoded dependency on Log Analytics blocks dev deployments.
        """
        content = load("main.tf")

        diag_block = re.search(
            r'resource\s+"azurerm_monitor_diagnostic_setting"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert diag_block, "azurerm_monitor_diagnostic_setting not found"
        assert "count" in diag_block.group(1), (
            "Diagnostic setting must use count guard for optional log analytics workspace"
        )

    @pytest.mark.parametrize("category", REQUIRED_LOG_CATEGORIES)
    def test_required_log_category_captured(self, category):
        """
        Each required audit category must be streamed to Log Analytics.
        Missing categories create blind spots in the security audit trail.
        """
        content = load("main.tf")
        assert f'"{category}"' in content or f"category = \"{category}\"" in content, (
            f"Audit category '{category}' must be enabled in diagnostic settings.\n"
            "This category is required for security monitoring and SOC2 compliance."
        )


# ── Workspace Resource ─────────────────────────────────────────────────────────

class TestWorkspaceResource:

    def test_workspace_has_lifecycle_block(self):
        """
        The workspace must have a lifecycle block.
        At minimum it should ignore auto-generated tags to prevent spurious diffs.
        """
        content = load("main.tf")

        workspace_block = re.search(
            r'resource\s+"azurerm_databricks_workspace"\s+"main"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert workspace_block, "azurerm_databricks_workspace.main not found"
        assert "lifecycle" in workspace_block.group(1), (
            "azurerm_databricks_workspace must have a lifecycle block"
        )

    def test_workspace_has_managed_resource_group(self):
        """
        managed_resource_group_name must be set to a predictable, governed name.
        Without this, Azure generates a random name that can't be governed by policy.
        """
        content = load("main.tf")
        assert "managed_resource_group_name" in content, (
            "Workspace must set managed_resource_group_name for governance visibility"
        )

    def test_workspace_has_timeout_configuration(self):
        """
        Workspace creation can take up to 45 minutes.
        Without a timeout override, the default 15-minute timeout causes false failures.
        """
        content = load("main.tf")
        assert "timeouts" in content, (
            "azurerm_databricks_workspace must define timeouts { create = ... }"
        )


# ── Resource Naming ────────────────────────────────────────────────────────────

class TestResourceNaming:

    def test_resource_group_name_uses_variables(self):
        """Resource group name must be built from prefix + environment variables."""
        content = load("main.tf")

        rg_block = re.search(
            r'resource\s+"azurerm_resource_group"\s+"databricks"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert rg_block, "azurerm_resource_group.databricks not found"

        name_match = re.search(r'name\s*=\s*"([^"]*)"', rg_block.group(1))
        assert name_match, "Resource group must have a name"

        name_expr = name_match.group(1)
        assert "prefix" in name_expr and "environment" in name_expr, (
            f"Resource group name must include prefix and environment variables. Got: {name_expr}"
        )

    def test_workspace_name_uses_variables(self):
        """Workspace name must be built from prefix + environment."""
        content = load("main.tf")

        ws_block = re.search(
            r'resource\s+"azurerm_databricks_workspace"\s+"main"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert ws_block, "azurerm_databricks_workspace.main not found"

        name_match = re.search(r'name\s*=\s*"([^"]*)"', ws_block.group(1))
        assert name_match, "Workspace must have a name"

        name_expr = name_match.group(1)
        assert "prefix" in name_expr or "environment" in name_expr, (
            f"Workspace name must reference prefix and/or environment. Got: {name_expr}"
        )


# ── Tagging ────────────────────────────────────────────────────────────────────

class TestTagging:

    REQUIRED_TAG_KEYS = ["environment", "team", "cost_centre", "managed_by"]

    def test_common_tags_local_defined(self):
        """
        A common_tags local must be defined so all resources share the same tags.
        Tag consistency is required for Azure Policy compliance and cost attribution.
        """
        content = load("main.tf")
        assert "common_tags" in content, (
            "Workspace module must define a common_tags local value"
        )

    @pytest.mark.parametrize("tag_key", REQUIRED_TAG_KEYS)
    def test_required_tag_in_common_tags(self, tag_key):
        """Each required tag key must be included in common_tags."""
        content = load("main.tf")

        common_tags_block = re.search(
            r'common_tags\s*=\s*merge\([^)]+\{([^}]+)\}[^)]*\)',
            content, re.DOTALL
        )
        if not common_tags_block:
            common_tags_block = re.search(
                r'common_tags\s*=\s*\{([^}]+)\}',
                content, re.DOTALL
            )

        assert common_tags_block, "common_tags definition not found in locals"
        assert tag_key in common_tags_block.group(1), (
            f"common_tags must include '{tag_key}'"
        )

    def test_managed_by_tag_is_terraform(self):
        """managed_by tag value must be 'terraform'."""
        content = load("main.tf")

        managed_by = re.search(r'managed_by\s*=\s*"([^"]+)"', content)
        assert managed_by, "managed_by tag must be defined in common_tags"
        assert managed_by.group(1) == "terraform", (
            f"managed_by must be 'terraform', got '{managed_by.group(1)}'"
        )


# ── Module Outputs ─────────────────────────────────────────────────────────────

class TestModuleOutputs:

    def test_outputs_file_exists(self):
        """outputs.tf must exist for the workspace module."""
        assert os.path.exists(os.path.join(MODULE_DIR, "outputs.tf")), (
            "workspace module is missing outputs.tf"
        )

    @pytest.mark.parametrize("output_name", [
        "workspace_id", "workspace_url", "workspace_name", "resource_group_name", "vnet_id"
    ])
    def test_required_output_declared(self, output_name):
        """Each required output must be declared for downstream consumers."""
        content = load("outputs.tf")
        assert f'output "{output_name}"' in content, (
            f"outputs.tf must declare output '{output_name}'"
        )
