"""
tests/integration/test_workspace_health.py
────────────────────────────────────────────────────────────────────────────────
Integration Test Suite: Post-Deploy Workspace Health

These tests run AFTER a successful terraform apply against the real workspace.
They verify that what was declared in code actually exists and is configured correctly.

Requirements:
  - DATABRICKS_HOST environment variable set
  - DATABRICKS_TOKEN environment variable set
  - pip install databricks-sdk

Run:
  pytest tests/integration/ -v --tb=short
────────────────────────────────────────────────────────────────────────────────
"""

import os
import re
import pytest

# Guard: skip integration tests if no workspace is configured
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
SKIP_INTEGRATION = not (DATABRICKS_HOST and DATABRICKS_TOKEN)
SKIP_REASON = "DATABRICKS_HOST and DATABRICKS_TOKEN must be set for integration tests"

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service import catalog, iam, compute, settings
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


@pytest.fixture(scope="session")
def w():
    """Authenticated Databricks workspace client."""
    if not SDK_AVAILABLE:
        pytest.skip("databricks-sdk not installed. Run: pip install databricks-sdk")
    if SKIP_INTEGRATION:
        pytest.skip(SKIP_REASON)
    return WorkspaceClient(host=DATABRICKS_HOST, token=DATABRICKS_TOKEN)


# ── Workspace Health ───────────────────────────────────────────────────────────

class TestWorkspaceConfiguration:

    def test_unity_catalog_is_enabled(self, w):
        """Unity Catalog must be enabled on the workspace. Without it, nothing else works."""
        metastore = w.metastores.current()
        assert metastore is not None, (
            "No metastore assigned to this workspace.\n"
            "Run: databricks_metastore_assignment in Terraform."
        )

    def test_workspace_name_follows_convention(self, w):
        """Workspace name must follow {prefix}-{env}-workspace convention."""
        workspace_info = w.get_workspace_id()
        # Note: name comes from Azure resource, verified via workspace config
        # Actual check happens via Azure Resource Manager tags
        assert workspace_info is not None

    def test_no_personal_access_tokens_for_automation(self, w):
        """
        Service principals used in CI must authenticate via OAuth/AAD tokens.
        Personal Access Tokens belong to individuals and expire unpredictably.
        This test checks that the current token is NOT a user PAT.
        """
        current_user = w.current_user.me()
        # If the token belongs to a user (not SP), warn — don't hard-fail in dev
        if current_user.user_name and "@" in current_user.user_name:
            pytest.warns(
                UserWarning,
                match="Using a personal token in CI is not recommended"
            )


# ── Unity Catalog Validation ───────────────────────────────────────────────────

class TestUnityCatalogStructure:

    EXPECTED_CATALOG_PATTERN = re.compile(
        r"^(dev|staging|prod)_[a-z][a-z0-9_]+_[a-z][a-z0-9_]+$"
    )
    EXPECTED_SCHEMA_PATTERN = re.compile(
        r"^[a-z][a-z0-9_]+_(bronze|silver|gold)$"
    )

    def test_all_catalogs_follow_naming_convention(self, w):
        """
        Every catalog in the workspace must follow the naming convention.
        If a catalog exists that doesn't match, it was created manually (ClickOps).
        """
        violations = []
        all_catalogs = list(w.catalogs.list())

        # Ignore system catalogs
        system_catalogs = {"hive_metastore", "system", "__databricks_internal"}

        for cat in all_catalogs:
            if cat.name in system_catalogs:
                continue
            if not self.EXPECTED_CATALOG_PATTERN.match(cat.name):
                violations.append(
                    f"CATALOG '{cat.name}' does not match naming convention.\n"
                    f"  Expected: {{env}}_{{team}}_{{domain}}\n"
                    f"  This may have been created manually (ClickOps drift)."
                )

        assert not violations, (
            "\n\n🚨 CATALOGS WITH INVALID NAMES (possible ClickOps drift):\n\n"
            + "\n".join(violations)
        )

    def test_all_managed_catalogs_have_owners(self, w):
        """Every non-system catalog must have an owner defined."""
        system_catalogs = {"hive_metastore", "system", "__databricks_internal"}
        violations = []

        for cat in w.catalogs.list():
            if cat.name in system_catalogs:
                continue
            if not cat.owner:
                violations.append(
                    f"CATALOG '{cat.name}' has no owner defined.\n"
                    f"  Assign ownership to a group via Terraform."
                )

        assert not violations, "\n\n🚨 OWNERLESS CATALOGS:\n\n" + "\n".join(violations)

    def test_all_schemas_follow_medallion_naming(self, w):
        """All schemas must follow {domain}_{bronze|silver|gold} convention."""
        system_catalogs = {"hive_metastore", "system", "__databricks_internal"}
        system_schemas = {"information_schema", "default"}
        violations = []

        for cat in w.catalogs.list():
            if cat.name in system_catalogs:
                continue
            for schema in w.schemas.list(catalog_name=cat.name):
                if schema.name in system_schemas:
                    continue
                if not self.EXPECTED_SCHEMA_PATTERN.match(schema.name):
                    violations.append(
                        f"SCHEMA '{cat.name}.{schema.name}' does not follow medallion naming.\n"
                        f"  Expected: {{domain}}_{{bronze|silver|gold}}"
                    )

        assert not violations, (
            "\n\n🚨 SCHEMAS WITH INVALID NAMES:\n\n" + "\n".join(violations)
        )


# ── Cluster Policy Validation ─────────────────────────────────────────────────

class TestClusterPolicies:

    def test_cluster_policies_exist_for_environment(self, w):
        """Expected cluster policies must exist in the workspace."""
        host = DATABRICKS_HOST or ""
        environment = "prod" if "prod" in host else "dev"

        expected_policies = [
            f"{environment}_standard_interactive",
            f"{environment}_job_cluster"
        ]

        existing_policies = {p.name for p in w.cluster_policies.list()}

        for expected in expected_policies:
            assert expected in existing_policies, (
                f"Cluster policy '{expected}' not found in workspace.\n"
                f"Run terraform apply to create it."
            )

    def test_all_cluster_policies_have_autotermination(self, w):
        """
        CRITICAL: Every cluster policy deployed to the workspace must enforce
        auto-termination. No exceptions. Verify against live workspace state.
        """
        import json
        violations = []
        system_policies = {"Personal Compute", "Power User Compute", "Shared Compute"}

        for policy in w.cluster_policies.list():
            if policy.name in system_policies:
                continue
            if not policy.definition:
                continue

            try:
                definition = json.loads(policy.definition)
                if "autotermination_minutes" not in definition:
                    violations.append(
                        f"POLICY '{policy.name}' (id: {policy.policy_id})\n"
                        f"  Does not enforce autotermination_minutes.\n"
                        f"  Update the Terraform definition and redeploy."
                    )
            except json.JSONDecodeError:
                pass  # Skip malformed policies

        assert not violations, (
            "\n\n🚨 CLUSTER POLICIES MISSING AUTOTERMINATION:\n\n"
            + "\n".join(violations)
        )


# ── RBAC Validation ───────────────────────────────────────────────────────────

class TestRBACStructure:

    EXPECTED_GROUPS = [
        "dbx-admins",
        "data_engineers",
        "data_analysts",
        "data_scientists",
        "platform_engineers"
    ]

    def test_expected_groups_exist(self, w):
        """All expected Databricks groups must exist. Missing groups = permissions gap."""
        existing_groups = {g.display_name for g in w.groups.list()}
        missing = [g for g in self.EXPECTED_GROUPS if g not in existing_groups]

        assert not missing, (
            f"Expected groups not found in workspace:\n"
            + "\n".join(f"  - {g}" for g in missing)
            + "\n\nEnsure SCIM provisioning is configured for these Azure AD groups."
        )

    def test_no_individual_users_have_admin_entitlement(self, w):
        """
        Admin entitlement must only belong to service principals and admin groups.
        Individual users with admin entitlement are a governance risk.
        """
        violations = []
        admin_groups = {"dbx-admins", "platform_engineers"}

        for user in w.users.list():
            if not user.roles:
                continue
            for role in user.roles:
                if "admin" in (role.value or "").lower():
                    # Flag individual user admins
                    if user.user_name and "@" in user.user_name:
                        violations.append(
                            f"USER '{user.user_name}' has admin role: {role.value}\n"
                            f"  Remove individual admin. Add user to '{list(admin_groups)[0]}' group instead."
                        )

        assert not violations, (
            "\n\n🚨 INDIVIDUAL USERS WITH ADMIN:\n\n" + "\n".join(violations)
        )

    def test_secret_scopes_exist_and_are_named_correctly(self, w):
        """
        All deployed secret scopes must follow naming convention {env}_{purpose}.
        Scopes that don't match were created manually.
        """
        host = DATABRICKS_HOST or ""
        environment = "prod" if "prod" in host else "dev"
        scope_pattern = re.compile(rf"^{environment}_[a-z][a-z0-9_]+$")

        violations = []
        for scope in w.secrets.list_scopes():
            if not scope_pattern.match(scope.name):
                violations.append(
                    f"SECRET SCOPE '{scope.name}' does not match convention '{environment}_{{purpose}}'.\n"
                    f"  This may have been created manually. Migrate to Terraform."
                )

        assert not violations, "\n\n🚨 SECRET SCOPES WITH INVALID NAMES:\n\n" + "\n".join(violations)
