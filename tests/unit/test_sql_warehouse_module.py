"""
tests/unit/test_sql_warehouse_module.py
────────────────────────────────────────────────────────────────────────────────
Unit Tests: sql-warehouse module

Validates:
  - Exactly two warehouses defined (analyst and engineering)
  - Both use PRO type (required for Unity Catalog)
  - Photon enabled on both
  - Auto-stop is always enforced (never 0)
  - Permissions grant CAN_USE only, never CAN_MANAGE
  - Permissions use dynamic blocks (no hardcoded groups)
  - Tags include cost attribution fields
  - Outputs declared for downstream consumers

Run locally:
  pytest tests/unit/test_sql_warehouse_module.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import pytest

MODULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "modules", "sql-warehouse")
)

PROD_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "environments", "prod")
)


def load(filename, base=None):
    path = os.path.join(base or MODULE_DIR, filename)
    assert os.path.exists(path), f"Expected file missing: {path}"
    return open(path, encoding="utf-8").read()


# ── Warehouse Definitions ──────────────────────────────────────────────────────

class TestWarehouseDefinitions:

    def test_analyst_warehouse_exists(self):
        """Analyst warehouse must be defined for BI and ad-hoc query workloads."""
        content = load("main.tf")
        assert 'databricks_sql_endpoint" "analyst"' in content, (
            "Module must define databricks_sql_endpoint.analyst"
        )

    def test_engineer_warehouse_exists(self):
        """Engineering warehouse must be defined for ETL validation and pipeline testing."""
        content = load("main.tf")
        assert 'databricks_sql_endpoint" "engineer"' in content, (
            "Module must define databricks_sql_endpoint.engineer"
        )

    def test_exactly_two_warehouses(self):
        """
        Exactly two warehouses: one for analysts, one for engineers.
        Separate warehouses prevent analyst dashboard queries from starving engineer workloads.
        """
        content = load("main.tf")
        count = len(re.findall(r'resource\s+"databricks_sql_endpoint"', content))
        assert count == 2, (
            f"Expected exactly 2 SQL warehouse resources, found {count}.\n"
            "Each function (analyst, engineering) requires its own warehouse."
        )

    def test_warehouse_names_use_environment_prefix(self):
        """Warehouse names must be prefixed with environment for multi-env clarity."""
        content = load("main.tf")

        name_lines = re.findall(r'name\s*=\s*"([^"]*)"', content)
        warehouse_names = [n for n in name_lines if "analyst" in n or "engineer" in n]

        for name in warehouse_names:
            assert "environment" in name or "${var.environment}" in name or "prod" in name or "${" in name, (
                f"Warehouse name '{name}' must include the environment variable as prefix"
            )


# ── Warehouse Type and Engine ──────────────────────────────────────────────────

class TestWarehouseConfiguration:

    def test_both_warehouses_use_pro_type(self):
        """
        Both warehouses must use PRO type.
        Unity Catalog row/column-level security only works with PRO warehouses.
        CLASSIC warehouses bypass Unity Catalog governance.
        """
        content = load("main.tf")

        pro_count = content.count('warehouse_type = "PRO"')
        assert pro_count == 2, (
            f"Both warehouses must have warehouse_type = \"PRO\". Found {pro_count} PRO declaration(s).\n"
            "CLASSIC warehouses do not enforce Unity Catalog access controls."
        )

    def test_photon_enabled_on_both_warehouses(self):
        """
        Photon (vectorised query engine) must be enabled on both warehouses.
        Photon delivers 2-8x speedup on SQL queries with no code changes.
        """
        content = load("main.tf")

        photon_count = content.count("enable_photon  = true") + content.count("enable_photon = true")
        assert photon_count == 2, (
            f"Both warehouses must have enable_photon = true. Found {photon_count} instance(s)."
        )

    def test_channel_set_to_current(self):
        """
        Warehouses must use CHANNEL_NAME_CURRENT (stable release).
        CHANNEL_NAME_PREVIEW may have breaking changes that disrupt production queries.
        """
        content = load("main.tf")
        assert "CHANNEL_NAME_CURRENT" in content, (
            "Warehouses must use channel name CHANNEL_NAME_CURRENT for production stability"
        )
        assert "CHANNEL_NAME_PREVIEW" not in content, (
            "CHANNEL_NAME_PREVIEW must not be used in production warehouses"
        )


# ── Auto-Stop Enforcement ──────────────────────────────────────────────────────

class TestAutoStop:

    def test_both_warehouses_have_auto_stop(self):
        """
        Both warehouses must configure auto_stop_mins.
        A warehouse left running with no queries costs money indefinitely.
        """
        content = load("main.tf")

        auto_stop_count = content.count("auto_stop_mins")
        assert auto_stop_count >= 2, (
            f"Expected auto_stop_mins on both warehouses. Found {auto_stop_count} instance(s)."
        )

    def test_auto_stop_variable_has_minimum_value_guard(self):
        """
        The auto_stop_mins variable must validate that the value is >= 1.
        Setting 0 disables auto-stop and creates an always-on warehouse.
        """
        content = load("variables.tf")

        # Both analyst and engineer auto_stop variables should have >= 1 validation
        validation_blocks = re.findall(
            r'variable\s+"[^"]*auto_stop_mins"[^}]+validation\s*\{([^}]+)\}',
            content, re.DOTALL
        )
        assert validation_blocks, (
            "auto_stop_mins variables must have a validation block preventing 0 or negative values"
        )
        for block in validation_blocks:
            assert ">= 1" in block or "> 0" in block, (
                f"auto_stop_mins validation must enforce >= 1. Got: {block.strip()}"
            )

    def test_engineer_auto_stop_longer_than_analyst(self):
        """
        The engineering warehouse default auto-stop should be longer than the analyst's.
        Engineers run longer-running queries; premature termination interrupts work.
        """
        content = load("variables.tf")

        analyst_default = re.search(
            r'variable\s+"analyst_auto_stop_mins"[^}]+default\s*=\s*(\d+)',
            content, re.DOTALL
        )
        engineer_default = re.search(
            r'variable\s+"engineer_auto_stop_mins"[^}]+default\s*=\s*(\d+)',
            content, re.DOTALL
        )
        assert analyst_default and engineer_default, (
            "Both auto_stop_mins variables must have default values"
        )
        assert int(engineer_default.group(1)) >= int(analyst_default.group(1)), (
            f"Engineering warehouse default auto-stop ({engineer_default.group(1)}min) must be >= "
            f"analyst default ({analyst_default.group(1)}min)."
        )


# ── Access Permissions ─────────────────────────────────────────────────────────

class TestWarehousePermissions:

    def test_permissions_blocks_defined_for_both_warehouses(self):
        """Each warehouse must have its own permissions block."""
        content = load("main.tf")

        perm_count = len(re.findall(r'resource\s+"databricks_permissions"', content))
        assert perm_count == 2, (
            f"Expected 2 databricks_permissions blocks (one per warehouse), found {perm_count}"
        )

    def test_permissions_grant_can_use_only(self):
        """
        Warehouse permissions must grant CAN_USE only.
        CAN_MANAGE would allow users to resize or delete warehouses managed by Terraform.
        """
        content = load("main.tf")

        assert "CAN_USE" in content, (
            "Warehouse permissions must grant CAN_USE"
        )

        # Check non-comment lines only
        violations = [
            line.strip() for line in content.splitlines()
            if "CAN_MANAGE" in line and not line.strip().startswith("#")
        ]
        assert not violations, (
            "CAN_MANAGE must not appear in non-comment lines of warehouse permissions.\n"
            "Warehouse configuration changes must go through Terraform.\n"
            f"Found: {violations}"
        )

    def test_permissions_use_dynamic_blocks(self):
        """
        Permissions must use dynamic blocks — groups come from variables, not hardcoded.
        """
        content = load("main.tf")

        perm_blocks = re.findall(
            r'resource\s+"databricks_permissions"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        for block in perm_blocks:
            assert "dynamic" in block or "for_each" in block, (
                "Warehouse permissions must use dynamic access_control blocks"
            )

    def test_no_hardcoded_email_principals(self):
        """Warehouse access must not be granted to individual email addresses."""
        content = load("main.tf")

        emails = re.findall(
            r'(group_name|principal)\s*=\s*"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"',
            content
        )
        assert not emails, (
            f"Warehouse module must not hardcode email principals: {emails}"
        )


# ── Cost Attribution Tags ──────────────────────────────────────────────────────

class TestWarehouseTags:

    def test_environment_tag_on_both_warehouses(self):
        """Warehouses must tag the environment for cost allocation filtering."""
        content = load("main.tf")
        env_tags = content.count('"environment"')
        assert env_tags >= 2, (
            "Both warehouses must include an environment custom tag"
        )

    def test_cost_centre_tag_on_both_warehouses(self):
        """Warehouses must tag cost_centre so their costs can be attributed to a budget."""
        content = load("main.tf")
        cc_tags = content.count('"cost_centre"')
        assert cc_tags >= 2, (
            "Both warehouses must include a cost_centre custom tag"
        )

    def test_managed_by_tag_on_both_warehouses(self):
        """managed_by = terraform must be present to identify Terraform-managed resources."""
        content = load("main.tf")
        managed_tags = content.count('"managed_by"')
        assert managed_tags >= 2, (
            "Both warehouses must include a managed_by custom tag"
        )

    def test_purpose_tag_distinguishes_warehouses(self):
        """
        Each warehouse must have a 'purpose' tag (analyst / engineering).
        This lets cost reports distinguish which team's queries drove spend.
        """
        content = load("main.tf")
        assert '"analyst"' in content and '"engineering"' in content, (
            "Warehouses must have distinct purpose tags ('analyst' and 'engineering')"
        )


# ── Module Outputs ─────────────────────────────────────────────────────────────

class TestWarehouseOutputs:

    def test_outputs_file_exists(self):
        assert os.path.exists(os.path.join(MODULE_DIR, "outputs.tf")), (
            "sql-warehouse module is missing outputs.tf"
        )

    @pytest.mark.parametrize("output_name", [
        "analyst_warehouse_id",
        "analyst_warehouse_jdbc_url",
        "engineer_warehouse_id",
        "engineer_warehouse_jdbc_url",
    ])
    def test_required_output_declared(self, output_name):
        """All warehouse connection details must be exported for downstream use."""
        content = load("outputs.tf")
        assert f'output "{output_name}"' in content, (
            f"outputs.tf must declare output '{output_name}'"
        )


# ── Prod Environment Wiring ────────────────────────────────────────────────────

class TestProdEnvironmentWiring:

    def test_sql_warehouses_module_called_from_prod(self):
        """sql_warehouses module must be included in the prod environment."""
        content = load("main.tf", base=PROD_DIR)
        assert 'module "sql_warehouses"' in content, (
            "prod/main.tf must call the sql_warehouses module"
        )

    def test_analyst_groups_include_analysts_and_engineers(self):
        """
        Analysts and engineers must both be in analyst_groups.
        Engineers need the analyst warehouse for query testing and validation.
        """
        content = load("main.tf", base=PROD_DIR)

        warehouse_block = re.search(
            r'module\s+"sql_warehouses"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert warehouse_block, "sql_warehouses module block not found in prod/main.tf"

        analyst_groups_line = re.search(
            r'analyst_groups\s*=\s*\[([^\]]+)\]',
            warehouse_block.group(1)
        )
        assert analyst_groups_line, "analyst_groups not defined in sql_warehouses module call"

        groups = analyst_groups_line.group(1)
        assert "lll-data-analysts" in groups, (
            "analyst_groups must include lll-data-analysts"
        )
        assert "lll-data-engineers" in groups, (
            "analyst_groups must include lll-data-engineers (for query validation)"
        )

    def test_engineer_groups_exclude_analysts(self):
        """
        Analysts must not be in engineer_groups.
        The engineering warehouse is for ETL workloads — analysts have no business need for it.
        """
        content = load("main.tf", base=PROD_DIR)

        warehouse_block = re.search(
            r'module\s+"sql_warehouses"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert warehouse_block, "sql_warehouses module block not found in prod/main.tf"

        engineer_groups_line = re.search(
            r'engineer_groups\s*=\s*\[([^\]]+)\]',
            warehouse_block.group(1)
        )
        assert engineer_groups_line, "engineer_groups not defined in sql_warehouses module call"

        groups = engineer_groups_line.group(1)
        assert "lll-data-analysts" not in groups, (
            "lll-data-analysts must NOT be in engineer_groups.\n"
            "Analysts do not run ETL pipelines."
        )
        assert "lll-data-engineers" in groups, (
            "lll-data-engineers must be in engineer_groups"
        )

    def test_prod_outputs_expose_warehouse_details(self):
        """prod/outputs.tf must export warehouse IDs for integration tests and BI tooling."""
        content = load("outputs.tf", base=PROD_DIR)

        for output in ["analyst_warehouse_id", "engineer_warehouse_id",
                       "analyst_warehouse_jdbc_url", "engineer_warehouse_jdbc_url"]:
            assert f'output "{output}"' in content, (
                f"prod/outputs.tf must declare output '{output}'"
            )
