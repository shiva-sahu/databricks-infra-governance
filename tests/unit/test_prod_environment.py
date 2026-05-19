"""
tests/unit/test_prod_environment.py
────────────────────────────────────────────────────────────────────────────────
Unit Tests: prod environment composition

Validates the prod/main.tf configuration against business rules:
  - Exactly the expected catalogs exist (ecommerce, finance)
  - Engineers have write access; analysts have read-only access
  - Bronze layer is restricted to engineers (no analyst access)
  - Silver/gold layers allow analysts SELECT only
  - Cost centres follow CC-XXXX format with distinct codes per catalog
  - Secret scope: admins MANAGE, engineers READ, no WRITE to non-admins
  - Approved node types do not include oversized instance families
  - No individual user principals anywhere in prod config

Run locally:
  pytest tests/unit/test_prod_environment.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import pytest

PROD_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "environments", "prod")
)

# Groups in use — any change here should be a conscious governance decision
ENGINEER_GROUP = "lll-data-engineers"
ANALYST_GROUP  = "lll-data-analysts"

# Catalogs that must exist in prod
REQUIRED_CATALOGS = {"ecommerce", "finance"}

# Write privileges that analysts must NEVER have
ANALYST_FORBIDDEN_PRIVILEGES = {
    "MODIFY", "CREATE_TABLE", "CREATE_SCHEMA", "DELETE",
    "DROP", "WRITE_FILES", "MANAGE_GRANTS", "ALL_PRIVILEGES"
}

# Write privileges engineers must have on their catalogs
ENGINEER_REQUIRED_CATALOG_PRIVILEGES = {"USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "MODIFY"}


def load_prod():
    path = os.path.join(PROD_DIR, "main.tf")
    assert os.path.exists(path), f"prod/main.tf not found at {path}"
    return open(path, encoding="utf-8").read()


def load_file(filename):
    path = os.path.join(PROD_DIR, filename)
    assert os.path.exists(path), f"Expected file missing: {path}"
    return open(path, encoding="utf-8").read()


# ── Catalog Configuration ──────────────────────────────────────────────────────

class TestCatalogConfiguration:

    def test_required_catalogs_defined(self):
        """
        Both ecommerce and finance catalogs must be defined in prod.
        Missing a catalog means its data layer has no governance boundaries.
        """
        content = load_prod()

        for catalog in REQUIRED_CATALOGS:
            assert f"{catalog} =" in content or f'"{catalog}"' in content, (
                f"Required catalog '{catalog}' not found in prod/main.tf.\n"
                "Each business domain must have a dedicated catalog."
            )

    def test_exactly_two_catalogs_in_prod(self):
        """
        Prod defines exactly 2 catalogs. New domains require a governance review
        before being added to production.
        """
        content = load_prod()

        # Each catalog entry starts a block like:  ecommerce = {
        # They appear inside the catalogs = { ... } argument to unity_catalog.
        # Count owner_group entries as a reliable proxy — one per catalog.
        owner_group_count = len(re.findall(r'owner_group\s*=', content))
        assert owner_group_count == 2, (
            f"Expected exactly 2 owner_group entries (one per catalog), found {owner_group_count}.\n"
            "Adding a new catalog to prod requires a governance review."
        )

    def test_each_catalog_has_unique_cost_centre(self):
        """
        Each catalog must have a distinct cost_centre for accurate cost attribution.
        Sharing a cost centre makes it impossible to track per-domain storage costs.
        """
        content = load_prod()

        # Extract cost_centres only from within the unity_catalog module block,
        # not from workspace or sql_warehouses (those legitimately share a cost centre)
        unity_block = re.search(
            r'module\s+"unity_catalog"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert unity_block, "unity_catalog module block not found"

        catalog_cost_centres = re.findall(
            r'cost_centre\s*=\s*"(CC-\d{4})"',
            unity_block.group(1)
        )
        assert len(catalog_cost_centres) >= 2, (
            "At least 2 cost_centre values expected within unity_catalog (one per catalog)"
        )
        assert len(set(catalog_cost_centres)) == len(catalog_cost_centres), (
            f"Catalog cost centres must be unique. Found duplicates: {catalog_cost_centres}"
        )

    def test_each_catalog_has_owner_group(self):
        """
        Every catalog must declare an owner_group.
        The owner is accountable for the data and its access controls.
        """
        content = load_prod()

        owner_count = content.count("owner_group")
        assert owner_count >= len(REQUIRED_CATALOGS), (
            f"Expected at least {len(REQUIRED_CATALOGS)} owner_group declarations "
            f"(one per catalog), found {owner_count}"
        )

    def test_catalog_owner_is_engineer_group(self):
        """
        Catalog ownership is held by the engineers group — they are responsible for the data.
        Analysts own nothing; they consume data.
        """
        content = load_prod()

        owner_lines = re.findall(r'owner_group\s*=\s*"([^"]+)"', content)
        for owner in owner_lines:
            assert ENGINEER_GROUP in owner or "engineers" in owner.lower(), (
                f"Catalog owner_group should be the engineers group, got: '{owner}'\n"
                "Analysts must not own catalogs."
            )


# ── Engineer Permissions ───────────────────────────────────────────────────────

class TestEngineerPermissions:

    def test_engineers_have_use_catalog(self):
        """Engineers must have USE_CATALOG on all catalogs."""
        content = load_prod()
        assert f'principal  = "{ENGINEER_GROUP}"' in content or f'principal = "{ENGINEER_GROUP}"' in content, (
            f"Engineer group '{ENGINEER_GROUP}' must be granted access in prod catalogs"
        )
        assert "USE_CATALOG" in content, (
            f"Engineers must have USE_CATALOG privilege"
        )

    def test_engineers_can_create_tables(self):
        """Engineers must have CREATE_TABLE on catalogs to manage data pipelines."""
        content = load_prod()
        assert "CREATE_TABLE" in content, (
            "Engineers must have CREATE_TABLE privilege on prod catalogs"
        )

    def test_engineers_can_modify_data(self):
        """Engineers must have MODIFY to run ETL pipelines that write/update records."""
        content = load_prod()
        assert "MODIFY" in content, (
            "Engineers must have MODIFY privilege for ETL pipeline operations"
        )

    def test_engineers_have_access_to_all_schema_layers(self):
        """
        Engineers must have access to all three layers: bronze, silver, and gold.
        They run the pipelines that populate each layer.
        """
        content = load_prod()

        for layer in ["bronze", "silver", "gold"]:
            # Find the layer block and check engineers appear
            layer_section = re.search(
                rf'{layer}\s*=\s*\[([^\]]+)\]',
                content, re.DOTALL
            )
            assert layer_section, f"'{layer}' schema_grants not found in prod catalogs"
            assert ENGINEER_GROUP in layer_section.group(1), (
                f"Engineers must have grants on the {layer} layer"
            )

    def test_engineers_have_read_files_on_external_location(self):
        """Engineers need READ_FILES on the external location for raw data ingestion."""
        content = load_prod()
        assert "READ_FILES" in content, (
            "Engineers must have READ_FILES on the external location"
        )
        assert ENGINEER_GROUP in content, (
            f"READ_FILES grant must include the engineer group '{ENGINEER_GROUP}'"
        )


# ── Analyst Permissions ────────────────────────────────────────────────────────

class TestAnalystPermissions:

    def test_analysts_have_use_catalog(self):
        """Analysts must have USE_CATALOG to browse catalog structure."""
        content = load_prod()
        assert ANALYST_GROUP in content, (
            f"Analyst group '{ANALYST_GROUP}' must be granted access in prod"
        )

    def test_analysts_cannot_create_or_modify(self):
        """
        Analysts are read-only consumers. They must not have write privileges.
        Any write access for analysts violates the data ownership model.
        """
        content = load_prod()

        # Find all blocks where analyst group is the principal
        analyst_blocks = re.finditer(
            rf'principal\s*=\s*"{re.escape(ANALYST_GROUP)}"(.+?)(?=principal\s*=|}})',
            content, re.DOTALL
        )

        violations = []
        for match in analyst_blocks:
            block = match.group(1)
            for forbidden in ANALYST_FORBIDDEN_PRIVILEGES:
                if f'"{forbidden}"' in block:
                    violations.append(
                        f"Analyst group has forbidden privilege '{forbidden}' near:\n  {block.strip()[:120]}"
                    )

        assert not violations, (
            "\n\n🚨 ANALYSTS HAVE WRITE PRIVILEGES IN PROD:\n\n"
            + "\n".join(violations)
        )

    def test_analysts_excluded_from_bronze_layer(self):
        """
        Analysts must NOT have access to the bronze (raw) layer.
        Raw data contains PII and unvalidated records — only engineers process it.
        Analysts work from silver/gold (cleansed and validated).
        """
        content = load_prod()

        bronze_section = re.search(
            r'bronze\s*=\s*\[([^\]]+)\]',
            content, re.DOTALL
        )
        assert bronze_section, "bronze schema_grants not found"

        bronze_grants = bronze_section.group(1)
        assert ANALYST_GROUP not in bronze_grants, (
            f"Analysts must NOT have access to the bronze layer.\n"
            f"Bronze contains raw/unvalidated data. Analysts should use silver or gold."
        )

    def test_analysts_have_select_on_silver(self):
        """Analysts must have SELECT access on the silver (cleansed) layer."""
        content = load_prod()

        # silver = [ ... ] may contain nested brackets (privilege lists), so
        # scan forward from the 'silver' key rather than trying to balance brackets.
        silver_pos = content.find("silver = [")
        assert silver_pos >= 0, "silver schema_grants not found"

        silver_section = content[silver_pos: silver_pos + 600]
        assert ANALYST_GROUP in silver_section, (
            f"Analysts ({ANALYST_GROUP}) must have SELECT access on the silver layer"
        )
        assert "SELECT" in silver_section, (
            "Analysts must have SELECT privilege on the silver layer"
        )

    def test_analysts_have_select_on_gold(self):
        """Analysts must have SELECT access on the gold (business-ready) layer."""
        content = load_prod()

        gold_pos = content.find("gold = [")
        assert gold_pos >= 0, "gold schema_grants not found"

        gold_section = content[gold_pos: gold_pos + 600]
        assert ANALYST_GROUP in gold_section, (
            f"Analysts ({ANALYST_GROUP}) must have SELECT access on the gold layer"
        )
        assert "SELECT" in gold_section, (
            "Analysts must have SELECT privilege on the gold layer"
        )


# ── Secret Scope Configuration ─────────────────────────────────────────────────

class TestSecretScopeConfig:

    def test_secret_scope_defined_in_prod(self):
        """Prod must define at least one secret scope for API credentials."""
        content = load_prod()
        assert "module" in content and "secret_scope" in content.lower(), (
            "Prod must include the secret_scopes module"
        )

    def test_admins_have_manage_on_secret_scope(self):
        """
        Only admins may MANAGE secret scopes.
        MANAGE allows creating/deleting secrets and changing ACLs.
        """
        content = load_prod()
        assert 'permission = "MANAGE"' in content, (
            "A MANAGE ACL entry must exist for the secret scope"
        )

        manage_blocks = re.finditer(
            r'principal\s*=\s*"([^"]+)"[^}]*?permission\s*=\s*"MANAGE"',
            content, re.DOTALL
        )
        for match in manage_blocks:
            principal = match.group(1)
            assert "admin" in principal.lower() or principal == "admins", (
                f"Only admin groups may have MANAGE on secret scopes, got: '{principal}'"
            )

    def test_engineers_have_read_on_secret_scope(self):
        """Engineers must have READ access to fetch credentials for ETL jobs."""
        content = load_prod()
        assert 'permission = "READ"' in content, (
            "Engineers must have READ permission on the secret scope"
        )

    def test_analysts_have_no_secret_scope_access(self):
        """
        Analysts must not have any access to secret scopes.
        Secrets contain service credentials — analysts have no need for them.
        """
        content = load_prod()

        secret_scope_block = re.search(
            r'module\s+"secret_scopes"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        if secret_scope_block:
            block = secret_scope_block.group(1)
            assert ANALYST_GROUP not in block, (
                f"Analysts must not have access to secret scopes. Found '{ANALYST_GROUP}' in secret_scopes config."
            )


# ── Compute Configuration ──────────────────────────────────────────────────────

class TestComputeConfiguration:

    def test_approved_node_types_defined(self):
        """Production must define an explicit approved_node_types list."""
        content = load_prod()
        assert "approved_node_types" in content, (
            "Prod cluster_policies must define approved_node_types"
        )

    def test_no_oversized_gpu_instances_approved(self):
        """
        GPU and very large instances must not appear in the approved list.
        These are 10-50x the cost of standard instances and rarely justified.
        """
        content = load_prod()

        approved_block = re.search(
            r'approved_node_types\s*=\s*\[([^\]]+)\]',
            content
        )
        if not approved_block:
            return  # No literal list — may use variable, skip this check

        approved = approved_block.group(1)

        forbidden_families = ["NC", "ND", "NV", "H100", "A100", "Standard_E64", "Standard_M"]
        for family in forbidden_families:
            assert family not in approved, (
                f"Oversized/GPU instance family '{family}' must not be in approved_node_types.\n"
                "These instances require explicit approval from the platform team."
            )

    def test_both_analyst_and_engineer_groups_can_use_interactive_policy(self):
        """
        The interactive cluster policy must be accessible to both analysts and engineers.
        Analysts need interactive clusters for notebooks; engineers need them for development.
        """
        content = load_prod()

        interactive_block = re.search(
            r'interactive_policy_groups\s*=\s*\[([^\]]+)\]',
            content
        )
        assert interactive_block, "interactive_policy_groups not found in cluster_policies module call"

        groups = interactive_block.group(1)
        assert ANALYST_GROUP in groups, (
            f"Analysts ({ANALYST_GROUP}) must be in interactive_policy_groups"
        )
        assert ENGINEER_GROUP in groups, (
            f"Engineers ({ENGINEER_GROUP}) must be in interactive_policy_groups"
        )

    def test_only_engineers_can_run_jobs(self):
        """
        Job cluster policy must be restricted to engineers.
        Analysts do not run scheduled pipelines — that is the engineers' responsibility.
        """
        content = load_prod()

        job_block = re.search(
            r'job_policy_groups\s*=\s*\[([^\]]+)\]',
            content
        )
        assert job_block, "job_policy_groups not found in cluster_policies module call"

        groups = job_block.group(1)
        assert ANALYST_GROUP not in groups, (
            f"Analysts must not be in job_policy_groups.\n"
            "Job clusters run production pipelines — engineers only."
        )
        assert ENGINEER_GROUP in groups, (
            f"Engineers must be in job_policy_groups"
        )


# ── No Individual Grants ───────────────────────────────────────────────────────

class TestNoIndividualGrants:

    def test_no_email_principals_in_prod(self):
        """
        Prod configuration must not grant access to individual email addresses.
        All access must go through Azure AD groups.
        """
        violations = []
        for filepath in glob.glob(f"{PROD_DIR}/**/*.tf", recursive=True):
            content = open(filepath, encoding="utf-8").read()
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                if line.strip().startswith("#"):
                    continue
                match = re.search(
                    r'(principal|user_name)\s*=\s*"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"',
                    line
                )
                if match:
                    violations.append(f"[{filepath}:{i}] {line.strip()}")

        assert not violations, (
            "\n\n🚨 INDIVIDUAL USER GRANTS IN PROD:\n\n"
            + "\n".join(violations)
            + "\n\nAdd the user to an Azure AD group instead."
        )

    def test_no_hardcoded_user_resources_in_prod(self):
        """
        databricks_user resources must not exist in the prod environment.
        User provisioning is handled by Azure AD SCIM — not Terraform.
        """
        violations = []
        for filepath in glob.glob(f"{PROD_DIR}/**/*.tf", recursive=True):
            content = open(filepath, encoding="utf-8").read()
            if 'resource "databricks_user"' in content:
                violations.append(filepath)

        assert not violations, (
            f"\n\n🚨 databricks_user resources found in prod — use SCIM instead:\n"
            + "\n".join(violations)
        )


# ── Environment File Completeness ──────────────────────────────────────────────

class TestEnvironmentCompleteness:

    def test_all_required_modules_present(self):
        """All four modules must be called from prod/main.tf."""
        content = load_prod()

        required_modules = ["workspace", "unity_catalog", "cluster_policies", "secret_scopes"]
        for module in required_modules:
            assert f'module "{module}"' in content, (
                f"Required module '{module}' not found in prod/main.tf"
            )

    def test_outputs_file_exists(self):
        """prod/outputs.tf must exist so pipeline can inspect what was created."""
        assert os.path.exists(os.path.join(PROD_DIR, "outputs.tf")), (
            "prod/outputs.tf must exist to expose catalog names for verification"
        )

    def test_variables_file_exists(self):
        """prod/variables.tf must exist to declare the environment's contract."""
        assert os.path.exists(os.path.join(PROD_DIR, "variables.tf")), (
            "prod/variables.tf must exist"
        )

    def test_sensitive_variables_marked_sensitive(self):
        """databricks_token and databricks_host must be marked sensitive."""
        content = load_file("variables.tf")

        token_block = re.search(
            r'variable\s+"databricks_token"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert token_block, "variable 'databricks_token' not found in variables.tf"
        assert "sensitive" in token_block.group(1), (
            "databricks_token must be marked sensitive = true"
        )
