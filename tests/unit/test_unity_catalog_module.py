"""
tests/unit/test_unity_catalog_module.py
────────────────────────────────────────────────────────────────────────────────
Unit Tests: unity-catalog module

Validates that the module definition itself is correct:
  - Exactly three schemas (bronze/silver/gold) per catalog
  - No hardcoded principals — all flow through variables
  - Optional resources guarded by count
  - Metastore ID handled safely (null, not empty string)
  - Lifecycle protections on long-lived infrastructure
  - Outputs declared for downstream consumers

Run locally:
  pytest tests/unit/test_unity_catalog_module.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import pytest

MODULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "modules", "unity-catalog")
)


def module_files():
    return glob.glob(f"{MODULE_DIR}/**/*.tf", recursive=True)


def load(filename):
    path = os.path.join(MODULE_DIR, filename)
    assert os.path.exists(path), f"Expected file missing: {path}"
    return open(path).read()


# ── Medallion Schema Structure ─────────────────────────────────────────────────

class TestSchemaCompleteness:

    def test_exactly_three_medallion_layers_defined(self):
        """
        The module must iterate exactly [bronze, silver, gold] — no more, no less.
        Adding a 'platinum' or 'raw' layer breaks the governance model.
        """
        content = load("main.tf")

        layers_match = re.search(r'for layer in \[([^\]]+)\]', content)
        assert layers_match, "Schema for_each must iterate over a layer list"

        layers_text = layers_match.group(1)
        found = set(re.findall(r'"([^"]+)"', layers_text))
        expected = {"bronze", "silver", "gold"}

        assert found == expected, (
            f"Schema layers must be exactly {expected}. Got: {found}\n"
            "Do not add non-standard layers. Raise a governance RFC instead."
        )

    def test_schema_name_references_domain_and_layer(self):
        """
        Schema names must be built from domain + layer, not hardcoded.
        Pattern: {domain}_{layer} e.g. ecommerce_bronze
        """
        content = load("main.tf")

        # Find the name line inside databricks_schema.schemas
        # It must reference both catalog.domain and layer
        assert "each.value.catalog.domain" in content or "catalog.domain" in content, (
            "Schema name must reference the catalog's domain field"
        )
        assert 'each.value.layer' in content, (
            "Schema name must reference the layer variable"
        )

    def test_schema_owner_comes_from_catalog_owner_group(self):
        """
        Schema owner must be the catalog's owner_group, not a hardcoded string.
        Owner drives billing accountability — it must match the catalog owner.
        """
        content = load("main.tf")

        owner_line = re.search(r'owner\s*=\s*(.+)', content)
        assert owner_line, "databricks_schema must set owner"

        owner_expr = owner_line.group(1).strip()
        assert "owner_group" in owner_expr, (
            f"Schema owner must reference owner_group from variable. Got: {owner_expr}"
        )

    def test_schema_properties_include_layer_and_domain(self):
        """Schema properties block must record layer and domain for in-UI discoverability."""
        content = load("main.tf")

        # Find properties block in schema resource
        schema_props = re.search(
            r'resource\s+"databricks_schema"[^{]+\{.*?properties\s*=\s*\{([^}]+)\}',
            content, re.DOTALL
        )
        assert schema_props, "databricks_schema must have a properties block"

        props = schema_props.group(1)
        assert "layer" in props, "Schema properties must include 'layer'"
        assert "domain" in props, "Schema properties must include 'domain'"
        assert "managed_by" in props, "Schema properties must include 'managed_by'"


# ── Grant Structure ────────────────────────────────────────────────────────────

class TestGrantStructure:

    def test_catalog_grants_use_dynamic_blocks(self):
        """
        Grants must use dynamic blocks — principals come from variables, never hardcoded.
        This lets environments compose grants without touching module code.
        """
        content = load("main.tf")

        catalog_grants_section = re.search(
            r'resource\s+"databricks_grants"\s+"catalog_grants"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert catalog_grants_section, "databricks_grants.catalog_grants must exist"
        assert "dynamic" in catalog_grants_section.group(1), (
            "catalog_grants must use a dynamic 'grant' block, not hardcoded principals"
        )

    def test_schema_grants_use_dynamic_blocks(self):
        """Schema grants also use dynamic blocks — same principle as catalog grants."""
        content = load("main.tf")

        schema_grants_section = re.search(
            r'resource\s+"databricks_grants"\s+"schema_grants"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert schema_grants_section, "databricks_grants.schema_grants must exist"
        assert "dynamic" in schema_grants_section.group(1), (
            "schema_grants must use a dynamic 'grant' block"
        )

    def test_schema_grants_filter_empty_lists(self):
        """
        Schema grants for_each must skip layers with no grants defined.
        An empty databricks_grants block is a Terraform error.
        """
        content = load("main.tf")

        # The schema_grants for_each must include a length filter
        schema_grants_section = re.search(
            r'resource\s+"databricks_grants"\s+"schema_grants"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert schema_grants_section, "databricks_grants.schema_grants must exist"
        block = schema_grants_section.group(1)

        assert "length" in block or "if " in block, (
            "schema_grants for_each must filter out empty grant lists (if length(item.grants) > 0)"
        )

    def test_no_hardcoded_principals_in_module(self):
        """
        The module must not contain hardcoded group names or emails as principals.
        Principals are supplied by the calling environment through variables.
        """
        content = load("main.tf")

        # Hardcoded email as principal
        email_grants = re.findall(
            r'principal\s*=\s*"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"',
            content
        )
        assert not email_grants, (
            f"Module must not hardcode email principals: {email_grants}\n"
            "Principals must come from var.catalogs[].grants[].principal"
        )

    def test_external_location_grants_exist(self):
        """External location grants resource must be defined for storage access control."""
        content = load("main.tf")
        assert 'databricks_grants" "external_location"' in content, (
            "Module must define databricks_grants.external_location"
        )

    def test_external_location_grants_conditional(self):
        """External location grants must only apply when the external location was created."""
        content = load("main.tf")

        ext_grants = re.search(
            r'resource\s+"databricks_grants"\s+"external_location"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert ext_grants, "databricks_grants.external_location not found"
        assert "count" in ext_grants.group(1) or "one(" in ext_grants.group(1), (
            "external_location grants must guard against non-existent external location"
        )


# ── Optional Resource Guards ───────────────────────────────────────────────────

class TestConditionalResources:

    def test_metastore_assignment_requires_both_ids(self):
        """
        Metastore assignment needs BOTH metastore_id AND workspace_numeric_id.
        Assigning with only one ID is a no-op that wastes a Terraform operation.
        """
        content = load("main.tf")

        assignment_block = re.search(
            r'resource\s+"databricks_metastore_assignment"\s+"this"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert assignment_block, "databricks_metastore_assignment.this not found"

        count_line = re.search(r'count\s*=\s*(.+)', assignment_block.group(1))
        assert count_line, "metastore_assignment must have a count guard"

        count_expr = count_line.group(1)
        assert "metastore_id" in count_expr and "workspace_numeric_id" in count_expr, (
            f"count guard must check both metastore_id and workspace_numeric_id. Got: {count_expr}"
        )

    def test_storage_credential_has_count_guard(self):
        """Storage credential must not be created when no access connector is configured."""
        content = load("main.tf")

        cred_block = re.search(
            r'resource\s+"databricks_storage_credential"\s+"adls"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert cred_block, "databricks_storage_credential.adls not found"
        assert "count" in cred_block.group(1), (
            "storage_credential must have a count guard (count = var.access_connector_id != \"\" ? 1 : 0)"
        )

    def test_external_location_has_count_guard(self):
        """External location must not be created when no access connector is configured."""
        content = load("main.tf")

        loc_block = re.search(
            r'resource\s+"databricks_external_location"\s+"main"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert loc_block, "databricks_external_location.main not found"
        assert "count" in loc_block.group(1), (
            "external_location must have a count guard"
        )

    def test_catalog_metastore_id_null_safe(self):
        """
        Catalog must not pass empty string for metastore_id.
        The Databricks provider rejects '' but accepts null (uses workspace default).
        """
        content = load("main.tf")

        # Find metastore_id specifically in the catalog resource, not in
        # databricks_metastore_assignment (which legitimately uses the raw var).
        catalog_start = content.find('resource "databricks_catalog" "catalogs"')
        assert catalog_start >= 0, "databricks_catalog.catalogs resource not found"

        catalog_section = content[catalog_start: catalog_start + 800]
        metastore_line = re.search(r'metastore_id\s*=\s*(.+)', catalog_section)
        assert metastore_line, "databricks_catalog must set metastore_id"

        expr = metastore_line.group(1).strip()
        assert "null" in expr or '!= ""' in expr or "!= ''" in expr, (
            f"catalog metastore_id must use null fallback when empty. Got: {expr}\n"
            "Use: var.metastore_id != \"\" ? var.metastore_id : null"
        )

    def test_storage_root_safe_reference(self):
        """
        storage_root must not directly index an empty list with [0].
        Use one() or a length check so the plan doesn't fail when the external location is absent.
        """
        content = load("main.tf")

        storage_root_line = re.search(r'storage_root\s*=\s*(.+)', content)
        assert storage_root_line, "databricks_catalog must set storage_root"

        expr = storage_root_line.group(1).strip()
        assert "main[0]" not in expr or "one(" in content, (
            f"storage_root must not use [0] directly on a count-based resource. Got: {expr}\n"
            "Use: one(databricks_external_location.main[*].url)"
        )


# ── Lifecycle Protections ──────────────────────────────────────────────────────

class TestLifecycleProtections:

    def test_storage_credential_prevent_destroy(self):
        """
        Storage credential deletion orphans every managed table that uses it.
        prevent_destroy is the last line of defence.
        """
        content = load("main.tf")

        cred_block = re.search(
            r'resource\s+"databricks_storage_credential"\s+"adls"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert cred_block, "databricks_storage_credential.adls not found"
        assert "prevent_destroy" in cred_block.group(1), (
            "storage_credential must have lifecycle { prevent_destroy = true }"
        )

    def test_external_location_prevent_destroy(self):
        """External location deletion invalidates all external tables. Must be protected."""
        content = load("main.tf")

        loc_block = re.search(
            r'resource\s+"databricks_external_location"\s+"main"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert loc_block, "databricks_external_location.main not found"
        assert "prevent_destroy" in loc_block.group(1), (
            "external_location must have lifecycle { prevent_destroy = true }"
        )


# ── Module Outputs ─────────────────────────────────────────────────────────────

class TestModuleOutputs:

    def test_outputs_file_exists(self):
        """outputs.tf must exist — callers need to reference catalog and schema names."""
        assert os.path.exists(os.path.join(MODULE_DIR, "outputs.tf")), (
            "unity-catalog module is missing outputs.tf"
        )

    def test_catalog_names_output_exists(self):
        """catalog_names output lets environments verify what was created."""
        content = load("outputs.tf")
        assert 'output "catalog_names"' in content, (
            "outputs.tf must declare output 'catalog_names'"
        )

    def test_schema_names_output_exists(self):
        """schema_names output is required by integration tests."""
        content = load("outputs.tf")
        assert 'output "schema_names"' in content, (
            "outputs.tf must declare output 'schema_names'"
        )

    def test_external_location_output_exists(self):
        """external_location_name output lets other modules reference the location."""
        content = load("outputs.tf")
        assert 'output "external_location_name"' in content, (
            "outputs.tf must declare output 'external_location_name'"
        )
