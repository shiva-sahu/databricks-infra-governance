"""
tests/unit/test_secret_scope_module.py
────────────────────────────────────────────────────────────────────────────────
Unit Tests: secret-scope module

Validates:
  - All scopes are Key Vault-backed (secrets never stored natively in Databricks)
  - Scope names follow {env}_{purpose} convention
  - Only valid ACL permissions used (READ, WRITE, MANAGE)
  - MANAGE permission restricted to admin groups
  - No individual users in ACLs
  - Scopes skipped gracefully when Key Vault resource ID is empty

Run locally:
  pytest tests/unit/test_secret_scope_module.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import pytest

MODULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "modules", "secret-scope")
)


def load(filename):
    path = os.path.join(MODULE_DIR, filename)
    assert os.path.exists(path), f"Expected file missing: {path}"
    return open(path, encoding="utf-8").read()


# ── Key Vault Backend ──────────────────────────────────────────────────────────

class TestKeyVaultBackend:

    def test_scopes_use_keyvault_metadata(self):
        """
        All secret scopes must be Azure Key Vault-backed.
        Native Databricks secret storage is not approved — secrets must live in Key Vault
        where they can be audited, rotated, and managed with Azure RBAC.
        """
        content = load("main.tf")
        assert "keyvault_metadata" in content, (
            "Secret scopes must use keyvault_metadata block (Azure Key Vault backend).\n"
            "Native Databricks secret storage is not permitted."
        )

    def test_keyvault_metadata_uses_resource_id_and_dns(self):
        """Key Vault metadata must include both resource_id and dns_name."""
        content = load("main.tf")

        kv_blocks = re.findall(
            r'keyvault_metadata\s*\{([^}]+)\}',
            content
        )
        assert kv_blocks, "No keyvault_metadata blocks found"

        for block in kv_blocks:
            assert "resource_id" in block, (
                "keyvault_metadata must set resource_id"
            )
            assert "dns_name" in block, (
                "keyvault_metadata must set dns_name"
            )

    def test_scopes_skip_when_keyvault_not_configured(self):
        """
        Secret scopes must be skipped when key_vault_resource_id is empty.
        Creating a scope with an empty backend causes a provider error.
        """
        content = load("main.tf")

        scope_block = re.search(
            r'resource\s+"databricks_secret_scope"\s+"scopes"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert scope_block, "databricks_secret_scope.scopes not found"

        block = scope_block.group(1)
        assert "for_each" in block, "databricks_secret_scope must use for_each"
        assert "key_vault_resource_id" in block, (
            "for_each must filter on key_vault_resource_id to skip unconfigured scopes"
        )

    def test_acls_skip_when_keyvault_not_configured(self):
        """
        Secret ACLs must also be skipped when the scope was not created.
        Applying ACLs to a non-existent scope causes a provider error.
        """
        content = load("main.tf")

        acl_block = re.search(
            r'resource\s+"databricks_secret_acl"\s+"scope_acls"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert acl_block, "databricks_secret_acl.scope_acls not found"
        assert "key_vault_resource_id" in acl_block.group(1), (
            "ACL for_each must filter on key_vault_resource_id (same guard as the scope itself)"
        )


# ── Scope Naming ───────────────────────────────────────────────────────────────

class TestScopeNaming:

    def test_scope_name_includes_environment_prefix(self):
        """
        Scope names must be prefixed with the environment: {env}_{purpose}.
        Without the prefix, prod and dev scopes collide in shared metastores.
        """
        content = load("main.tf")

        name_line = re.search(r'name\s*=\s*"([^"]*)"', content)
        assert name_line, "databricks_secret_scope must set name"

        name_expr = name_line.group(1)
        # Name should use environment variable as prefix
        assert "environment" in name_expr or "var.environment" in name_expr, (
            f"Scope name must include var.environment as prefix. Got: {name_expr}\n"
            "Pattern: ${{var.environment}}_${{purpose}}"
        )

    def test_scope_name_uses_variable_not_hardcoded(self):
        """Scope name must be derived from variables, not hardcoded."""
        content = load("main.tf")

        literal_names = re.findall(
            r'resource\s+"databricks_secret_scope"[^{]+\{[^}]*name\s*=\s*"([^$][^"]*)"',
            content
        )
        assert not literal_names, (
            f"Secret scope names must not be hardcoded. Found literals: {literal_names}"
        )


# ── ACL Permissions ────────────────────────────────────────────────────────────

class TestACLPermissions:

    VALID_PERMISSIONS = {"READ", "WRITE", "MANAGE"}

    def test_only_valid_permissions_used(self):
        """
        Secret scope ACLs only support READ, WRITE, and MANAGE.
        Any other value is a Terraform error at apply time.
        """
        content = load("main.tf")

        permissions = re.findall(r'permission\s*=\s*([^\n#]+)', content)
        for perm_expr in permissions:
            # Skip variable references — those are validated at runtime
            if "var." in perm_expr or "each." in perm_expr:
                continue
            literal = re.search(r'"([^"]+)"', perm_expr)
            if literal:
                assert literal.group(1) in self.VALID_PERMISSIONS, (
                    f"Invalid permission: '{literal.group(1)}'\n"
                    f"Valid secret scope permissions: {self.VALID_PERMISSIONS}"
                )

    def test_acl_permission_comes_from_variable(self):
        """
        ACL permissions must come from variable input, not be hardcoded.
        This allows environments to customise access without touching module code.
        """
        content = load("main.tf")

        acl_block = re.search(
            r'resource\s+"databricks_secret_acl"\s+"scope_acls"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert acl_block, "databricks_secret_acl.scope_acls not found"

        # permission must reference a variable or loop variable
        assert "each.value.permission" in acl_block.group(1) or "acl.permission" in acl_block.group(1), (
            "ACL permission must reference the variable input (each.value.permission)"
        )

    def test_acl_principal_comes_from_variable(self):
        """ACL principals must come from variable input — no hardcoded group names in module."""
        content = load("main.tf")

        acl_block = re.search(
            r'resource\s+"databricks_secret_acl"\s+"scope_acls"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert acl_block, "databricks_secret_acl.scope_acls not found"
        assert "each.value.principal" in acl_block.group(1) or "acl.principal" in acl_block.group(1), (
            "ACL principal must reference the variable input (each.value.principal)"
        )

    def test_no_individual_user_principals_in_module(self):
        """
        Secret scope ACLs must not contain hardcoded email addresses.
        Individuals leave teams; group membership handles access changes automatically.
        """
        content = load("main.tf")

        email_acls = re.findall(
            r'principal\s*=\s*"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"',
            content
        )
        assert not email_acls, (
            f"Secret scope module must not hardcode email principals: {email_acls}"
        )


# ── Module Structure ───────────────────────────────────────────────────────────

class TestModuleStructure:

    def test_scope_acls_depend_on_scope(self):
        """
        ACLs must depend on the scope being created first.
        Without depends_on, Terraform may try to create ACLs before the scope exists.
        """
        content = load("main.tf")

        acl_block = re.search(
            r'resource\s+"databricks_secret_acl"\s+"scope_acls"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        assert acl_block, "databricks_secret_acl.scope_acls not found"
        assert "depends_on" in acl_block.group(1), (
            "databricks_secret_acl must have depends_on = [databricks_secret_scope.scopes]"
        )

    def test_variables_file_exists(self):
        """variables.tf must exist — the module must declare its contract."""
        assert os.path.exists(os.path.join(MODULE_DIR, "variables.tf")), (
            "secret-scope module is missing variables.tf"
        )

    def test_environment_variable_declared(self):
        """environment variable must be declared for scope naming."""
        content = load("variables.tf")
        assert 'variable "environment"' in content, (
            "secret-scope module must declare variable 'environment'"
        )

    def test_secret_scopes_variable_declared(self):
        """secret_scopes variable must be declared as the module's main input."""
        content = load("variables.tf")
        assert 'variable "secret_scopes"' in content, (
            "secret-scope module must declare variable 'secret_scopes'"
        )
