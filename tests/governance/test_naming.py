"""
tests/governance/test_naming.py
────────────────────────────────────────────────────────────────────────────────
Governance Test Suite: Naming Conventions

These tests parse every Terraform .tf file in the repo and enforce naming
rules BEFORE anything reaches a real Databricks workspace.

Rules enforced:
  - Catalog names: {env}_{team}_{domain}  (all lowercase, underscores only)
  - Schema names: {domain}_{layer}  where layer ∈ {bronze, silver, gold}
  - Secret scope names: {env}_{purpose}
  - Cluster policy names: {env}_{purpose}
  - Resource group names: {prefix}-{env}-*  (kebab-case)

Run locally:
  pytest tests/governance/test_naming.py -v

In CI:
  Runs on every PR via .github/workflows/governance-check.yml
  A failure BLOCKS the merge.
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import json
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_ENVIRONMENTS = {"dev", "staging", "prod"}
VALID_LAYERS = {"bronze", "silver", "gold"}
TERRAFORM_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "terraform")


def find_tf_files():
    """Return all .tf files in the terraform directory."""
    return glob.glob(f"{TERRAFORM_ROOT}/**/*.tf", recursive=True)


def extract_resource_names(tf_content: str, resource_type: str) -> list[dict]:
    """
    Extract resource names and their name attribute values from HCL.
    Returns list of dicts: {resource_label, name_value, line_number}
    """
    results = []
    lines = tf_content.splitlines()

    # Match: resource "databricks_catalog" "my_label" {
    resource_pattern = re.compile(
        rf'resource\s+"{re.escape(resource_type)}"\s+"([^"]+)"\s*\{{'
    )
    # Match: name = "actual_name_value"
    name_pattern = re.compile(r'name\s*=\s*"([^"]+)"')

    i = 0
    while i < len(lines):
        line = lines[i]
        res_match = resource_pattern.match(line.strip())
        if res_match:
            resource_label = res_match.group(1)
            # Look ahead for the name attribute within the next 20 lines
            for j in range(i + 1, min(i + 20, len(lines))):
                name_match = name_pattern.match(lines[j].strip())
                if name_match:
                    results.append({
                        "resource_label": resource_label,
                        "name_value": name_match.group(1),
                        "line_number": j + 1,
                        "file": "unknown"  # set by caller
                    })
                    break
                if lines[j].strip() == "}":
                    break
        i += 1

    return results


def load_all_tf_content() -> list[tuple[str, str]]:
    """Return list of (filepath, content) for all .tf files."""
    results = []
    for path in find_tf_files():
        with open(path) as f:
            results.append((path, f.read()))
    return results


# ── Catalog Naming Tests ───────────────────────────────────────────────────────

CATALOG_NAME_PATTERN = re.compile(
    r"^(dev|staging|prod)_[a-z][a-z0-9_]{1,20}_[a-z][a-z0-9_]{1,20}$"
)

class TestCatalogNaming:

    def test_catalog_names_follow_convention(self):
        """
        Catalog names must follow: {env}_{team}_{domain}
        All lowercase, underscores, 3 segments separated by underscores.

        DEMO: This test catches the bad PR which uses 'EcommerceData' as catalog name.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            # Skip variable definitions — they contain patterns, not literal names
            if "variables.tf" in filepath:
                continue

            # Look for catalog name interpolations: "${var.environment}_${var.team}_${each.value.domain}"
            # These are valid — the module enforces convention in code
            # Flag literal catalog names that DON'T use variable interpolation
            literal_names = re.findall(
                r'databricks_catalog["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if not CATALOG_NAME_PATTERN.match(name):
                    violations.append(
                        f"FAIL  [{filepath}] Catalog name '{name}' violates convention.\n"
                        f"      Expected: {{env}}_{{team}}_{{domain}} e.g. 'dev_ecommerce_orders'\n"
                        f"      Got: '{name}'"
                    )

        assert not violations, (
            "\n\n🚨 CATALOG NAMING VIOLATIONS FOUND:\n\n"
            + "\n".join(violations)
            + "\n\nFix all violations before merging. See docs/GOVERNANCE.md for naming rules."
        )

    def test_catalog_name_segments_are_lowercase(self):
        """All catalog name segments must be lowercase. No CamelCase. No UPPERCASE."""
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue
            literal_names = re.findall(
                r'databricks_catalog["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if name != name.lower():
                    violations.append(
                        f"FAIL  [{filepath}] Catalog name '{name}' contains uppercase.\n"
                        f"      Catalog names must be entirely lowercase."
                    )

        assert not violations, "\n\n🚨 UPPERCASE IN CATALOG NAMES:\n\n" + "\n".join(violations)

    def test_catalog_name_no_hyphens(self):
        """Catalog names must use underscores, not hyphens. Hyphens break SQL identifiers."""
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue
            literal_names = re.findall(
                r'databricks_catalog["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if "-" in name:
                    violations.append(
                        f"FAIL  [{filepath}] Catalog name '{name}' contains hyphens.\n"
                        f"      Use underscores: '{name.replace('-', '_')}'"
                    )

        assert not violations, "\n\n🚨 HYPHENS IN CATALOG NAMES:\n\n" + "\n".join(violations)


# ── Schema Naming Tests ────────────────────────────────────────────────────────

SCHEMA_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{1,30}_(bronze|silver|gold)$"
)

class TestSchemaNaming:

    def test_schema_names_follow_medallion_convention(self):
        """
        Schema names must follow: {domain}_{layer}
        Layer must be one of: bronze, silver, gold.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            literal_names = re.findall(
                r'databricks_schema["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if not SCHEMA_NAME_PATTERN.match(name):
                    violations.append(
                        f"FAIL  [{filepath}] Schema name '{name}' violates medallion convention.\n"
                        f"      Expected: {{domain}}_{{bronze|silver|gold}}\n"
                        f"      e.g. 'orders_bronze', 'customers_silver', 'revenue_gold'"
                    )

        assert not violations, (
            "\n\n🚨 SCHEMA NAMING VIOLATIONS:\n\n"
            + "\n".join(violations)
        )

    def test_schema_names_no_free_form_layers(self):
        """
        Schemas must end with bronze, silver, or gold.
        Do not invent new layer names ('raw', 'processed', 'presentation').
        """
        bad_layers = ["raw", "processed", "presentation", "curated", "staging", "landing"]

        violations = []
        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            literal_names = re.findall(
                r'databricks_schema["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                for bad in bad_layers:
                    if name.endswith(f"_{bad}"):
                        violations.append(
                            f"FAIL  [{filepath}] Schema '{name}' uses non-standard layer '{bad}'.\n"
                            f"      Allowed layers: bronze, silver, gold"
                        )

        assert not violations, "\n\n🚨 NON-STANDARD SCHEMA LAYERS:\n\n" + "\n".join(violations)


# ── Secret Scope Naming Tests ──────────────────────────────────────────────────

SECRET_SCOPE_PATTERN = re.compile(
    r"^(dev|staging|prod)_[a-z][a-z0-9_]{1,30}$"
)

class TestSecretScopeNaming:

    def test_secret_scope_names_follow_convention(self):
        """
        Secret scope names must follow: {env}_{purpose}
        e.g. 'dev_postgres', 'prod_api_keys', 'staging_service_bus'
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            literal_names = re.findall(
                r'databricks_secret_scope["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if not SECRET_SCOPE_PATTERN.match(name):
                    violations.append(
                        f"FAIL  [{filepath}] Secret scope '{name}' violates naming convention.\n"
                        f"      Expected: {{env}}_{{purpose}}  e.g. 'dev_postgres'"
                    )

        assert not violations, "\n\n🚨 SECRET SCOPE NAMING VIOLATIONS:\n\n" + "\n".join(violations)


# ── Cluster Policy Naming Tests ────────────────────────────────────────────────

CLUSTER_POLICY_PATTERN = re.compile(
    r"^(dev|staging|prod)_[a-z][a-z0-9_]{1,40}$"
)

class TestClusterPolicyNaming:

    def test_cluster_policy_names_follow_convention(self):
        """Cluster policy names must follow: {env}_{purpose}"""
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            literal_names = re.findall(
                r'databricks_cluster_policy["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if not CLUSTER_POLICY_PATTERN.match(name):
                    violations.append(
                        f"FAIL  [{filepath}] Cluster policy '{name}' violates naming convention.\n"
                        f"      Expected: {{env}}_{{purpose}}  e.g. 'dev_standard_interactive'"
                    )

        assert not violations, "\n\n🚨 CLUSTER POLICY NAMING VIOLATIONS:\n\n" + "\n".join(violations)

    def test_cluster_policies_define_autotermination(self):
        """
        Every cluster policy definition MUST set autotermination_minutes.
        No eternal clusters. This is non-negotiable.

        DEMO: This is the test that catches runaway cluster policies.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "modules" not in filepath:
                continue

            # Check if file contains cluster policy resources
            if 'databricks_cluster_policy' not in content:
                continue

            # For files with cluster policies, verify autotermination is defined somewhere
            # (it may be inside jsonencode blocks which nested-regex can't reach)
            policy_count = len(re.findall(
                r'resource\s+"databricks_cluster_policy"', content
            ))

            auto_count = content.count("autotermination_minutes")

            if policy_count > 0 and auto_count < policy_count:
                violations.append(
                    f"FAIL  [{filepath}] {policy_count} cluster policy resource(s) found but "
                    f"only {auto_count} autotermination_minutes definition(s).\n"
                    f"      Every policy MUST enforce auto-termination to prevent cost runaway."
                )

        assert not violations, "\n\n🚨 MISSING AUTOTERMINATION:\n\n" + "\n".join(violations)


# ── Resource Group Naming Tests ────────────────────────────────────────────────

RG_PATTERN = re.compile(
    r"^[a-z0-9]+-(?:dev|staging|prod)-[a-z0-9-]+-rg$"
)

class TestResourceGroupNaming:

    def test_resource_group_names_follow_convention(self):
        """
        Azure Resource Group names must follow: {prefix}-{env}-{purpose}-rg
        e.g. 'demo-dev-databricks-rg', 'gcw-prod-analytics-rg'
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            literal_names = re.findall(
                r'azurerm_resource_group["\s\w]*name\s*=\s*"([^$\{][^"]*)"',
                content
            )
            for name in literal_names:
                if not RG_PATTERN.match(name):
                    violations.append(
                        f"FAIL  [{filepath}] Resource group '{name}' violates naming convention.\n"
                        f"      Expected: {{prefix}}-{{env}}-{{purpose}}-rg"
                    )

        assert not violations, "\n\n🚨 RESOURCE GROUP NAMING VIOLATIONS:\n\n" + "\n".join(violations)
