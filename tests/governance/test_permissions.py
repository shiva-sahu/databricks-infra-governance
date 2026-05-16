"""
tests/governance/test_permissions.py
────────────────────────────────────────────────────────────────────────────────
Governance Test Suite: Permission Boundaries

These tests enforce permission rules across all Terraform configurations.
They catch the most dangerous mistakes BEFORE they reach production:
  - Overly broad grants (ALL PRIVILEGES)
  - Prod access granted to dev groups
  - Individuals granted direct access (bypass group management)
  - Escalation of privilege beyond role boundaries

Run locally:
  pytest tests/governance/test_permissions.py -v

DEMO MOMENT: Open the bad-pr branch — test_no_all_privileges will FAIL
             with a clear message showing exactly what's wrong.
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import json
import pytest
from pathlib import Path

TERRAFORM_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "terraform")
ENVIRONMENTS_ROOT = os.path.join(TERRAFORM_ROOT, "environments")


def find_tf_files(root=None):
    root = root or TERRAFORM_ROOT
    return glob.glob(f"{root}/**/*.tf", recursive=True)


def load_all_tf_content(root=None):
    return [(p, open(p).read()) for p in find_tf_files(root)]


# ── ALL PRIVILEGES Guard ───────────────────────────────────────────────────────

class TestNoAllPrivileges:

    def test_no_all_privileges_in_catalog_grants(self):
        """
        'ALL PRIVILEGES' must NEVER appear in a databricks_grants block.

        Why: ALL PRIVILEGES gives uncontrolled write/drop/manage access.
        It eliminates audit clarity and violates least-privilege.
        If you think you need ALL PRIVILEGES, you need a different architecture.

        ══════════════════════════════════════════════════════════
        DEMO BREAKAGE POINT: This test will FAIL on demo/bad-pr
        because that branch grants ALL PRIVILEGES to data_analysts.
        ══════════════════════════════════════════════════════════
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "ALL PRIVILEGES" in content or "ALL_PRIVILEGES" in content:
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    if "ALL PRIVILEGES" in line or "ALL_PRIVILEGES" in line:
                        # Don't flag comments explaining the rule
                        if line.strip().startswith("#"):
                            continue
                        # Don't flag validation error_message strings (they reference the term to explain the rule)
                        if "error_message" in line or "contains(g.privileges" in line:
                            continue
                        # Don't flag lines in test files themselves
                        if "tests/" in filepath:
                            continue
                        violations.append(
                            f"FAIL  [{filepath}:{i}]\n"
                            f"      Line: {line.strip()}\n"
                            f"      'ALL PRIVILEGES' is forbidden. Use explicit privilege lists.\n"
                            f"      e.g. [\"USE_CATALOG\", \"CREATE_TABLE\", \"SELECT\", \"MODIFY\"]"
                        )

        assert not violations, (
            "\n\n🚨 ALL PRIVILEGES DETECTED — THIS MERGE IS BLOCKED:\n\n"
            + "\n\n".join(violations)
            + "\n\n"
            + "═" * 60 + "\n"
            + "WHY THIS IS BLOCKED:\n"
            + "ALL PRIVILEGES grants unrestricted access including DROP TABLE,\n"
            + "MANAGE GRANTS (privilege escalation), and future privileges.\n"
            + "It bypasses the audit trail and violates SOC2 least-privilege requirements.\n"
            + "═" * 60
        )

    def test_no_wildcard_grants(self):
        """No wildcard (*) privilege patterns in any grant."""
        violations = []

        for filepath, content in load_all_tf_content():
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                # Match privileges = ["*"] or privileges = ["*", ...]
                if re.search(r'privileges\s*=\s*\[.*"\*".*\]', line):
                    violations.append(
                        f"FAIL  [{filepath}:{i}] Wildcard privilege grant detected: {line.strip()}"
                    )

        assert not violations, "\n\n🚨 WILDCARD PRIVILEGES:\n\n" + "\n".join(violations)


# ── Production Permission Boundary Tests ──────────────────────────────────────

class TestProductionBoundaries:

    def test_dev_team_cannot_modify_prod_catalogs(self):
        """
        The 'dev_team' group must NOT have MODIFY, CREATE_TABLE, DELETE,
        or MANAGE GRANTS on any prod catalog.

        Dev teams can READ production data for debugging.
        They cannot write to it.
        """
        prod_tf_files = load_all_tf_content(
            root=os.path.join(ENVIRONMENTS_ROOT, "prod")
        )

        write_privileges = {
            "MODIFY", "CREATE_TABLE", "CREATE_SCHEMA", "DELETE",
            "MANAGE_GRANTS", "ALL PRIVILEGES", "ALL_PRIVILEGES", "WRITE_FILES"
        }

        violations = []

        for filepath, content in prod_tf_files:
            lines = content.splitlines()

            # Scan for dev_team being granted write privileges
            in_dev_team_block = False
            for i, line in enumerate(lines, 1):
                if '"dev_team"' in line or "'dev_team'" in line:
                    in_dev_team_block = True

                if in_dev_team_block:
                    for priv in write_privileges:
                        if f'"{priv}"' in line or f"'{priv}'" in line:
                            violations.append(
                                f"FAIL  [{filepath}:{i}]\n"
                                f"      dev_team granted '{priv}' in PROD environment.\n"
                                f"      dev_team may only have SELECT/USE_CATALOG/USE_SCHEMA in prod."
                            )

                if line.strip() == "}" and in_dev_team_block:
                    in_dev_team_block = False

        assert not violations, (
            "\n\n🚨 PROD PERMISSION BOUNDARY VIOLATION:\n\n"
            + "\n\n".join(violations)
        )

    def test_no_individual_user_grants(self):
        """
        Grants must be to GROUPS, not individual users.

        Individual grants:
        - Break when people change teams
        - Are invisible to group-based access reviews
        - Cannot be managed at scale
        - Violate the principle that permissions are role-based, not person-based

        Use Azure AD groups + SCIM. If a person needs access, add them to a group.
        """
        violations = []

        # Individual user indicators: user emails, user: prefix
        individual_patterns = [
            r'principal\s*=\s*"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"',
            r'user_name\s*=\s*"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"',
        ]

        # Exception: service principals are ok as they are system identities
        sp_pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

        for filepath, content in load_all_tf_content():
            # Skip examples and test fixtures
            if "example" in filepath.lower() or "fixture" in filepath.lower():
                continue

            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                if line.strip().startswith("#"):
                    continue
                for pattern in individual_patterns:
                    match = re.search(pattern, line)
                    if match:
                        email = re.search(r'"([^"]+@[^"]+)"', line)
                        if email and not sp_pattern.search(email.group(1)):
                            violations.append(
                                f"FAIL  [{filepath}:{i}]\n"
                                f"      Individual user grant detected: {line.strip()}\n"
                                f"      Grants must target GROUPS, not individuals.\n"
                                f"      Add the user to an appropriate Azure AD group instead."
                            )

        assert not violations, (
            "\n\n🚨 INDIVIDUAL USER GRANTS DETECTED:\n\n"
            + "\n\n".join(violations)
        )


# ── Privilege Escalation Prevention ───────────────────────────────────────────

class TestPrivilegeEscalation:

    def test_non_admin_groups_cannot_manage_grants(self):
        """
        MANAGE GRANTS privilege allows a principal to grant ANY privilege
        to ANY other principal on that object — effectively making them an admin.

        Only DBA/admin groups may hold MANAGE GRANTS.
        """
        allowed_manage_grant_groups = {
            "dbx-admins",
            "platform_engineers",
            "dba_team"
        }

        violations = []

        for filepath, content in load_all_tf_content():
            lines = content.splitlines()
            current_principal = None

            for i, line in enumerate(lines, 1):
                # Track current principal
                principal_match = re.search(r'principal\s*=\s*"([^"]+)"', line)
                if principal_match:
                    current_principal = principal_match.group(1)

                # Check for MANAGE GRANTS
                if "MANAGE GRANTS" in line or "MANAGE_GRANTS" in line:
                    if line.strip().startswith("#"):
                        continue
                    if current_principal and current_principal not in allowed_manage_grant_groups:
                        violations.append(
                            f"FAIL  [{filepath}:{i}]\n"
                            f"      MANAGE GRANTS assigned to '{current_principal}'.\n"
                            f"      Only these groups may hold MANAGE GRANTS:\n"
                            f"      {sorted(allowed_manage_grant_groups)}"
                        )

        assert not violations, (
            "\n\n🚨 UNAUTHORIZED MANAGE GRANTS:\n\n"
            + "\n\n".join(violations)
        )

    def test_analysts_cannot_create_or_drop_tables(self):
        """
        Analyst groups (data_analysts, finance_analysts, etc.) are read-only.
        They must not have CREATE_TABLE, MODIFY, or DELETE on schemas.
        """
        analyst_pattern = re.compile(r'.*_analysts?$')
        write_privileges = {"CREATE_TABLE", "MODIFY", "DELETE", "DROP", "WRITE_FILES"}

        violations = []

        for filepath, content in load_all_tf_content():
            lines = content.splitlines()
            current_principal = None

            for i, line in enumerate(lines, 1):
                if line.strip().startswith("#"):
                    continue

                principal_match = re.search(r'principal\s*=\s*"([^"]+)"', line)
                if principal_match:
                    current_principal = principal_match.group(1)

                if current_principal and analyst_pattern.match(current_principal):
                    for priv in write_privileges:
                        if f'"{priv}"' in line:
                            violations.append(
                                f"FAIL  [{filepath}:{i}]\n"
                                f"      Analyst group '{current_principal}' granted write privilege '{priv}'.\n"
                                f"      Analyst groups are read-only: SELECT, USE_CATALOG, USE_SCHEMA only."
                            )

        assert not violations, (
            "\n\n🚨 ANALYSTS GRANTED WRITE PRIVILEGES:\n\n"
            + "\n\n".join(violations)
        )


# ── Secret Scope Permission Tests ──────────────────────────────────────────────

class TestSecretScopePermissions:

    def test_secret_scope_acls_use_valid_permissions(self):
        """Secret scope ACL permissions must be READ, WRITE, or MANAGE only."""
        valid_permissions = {"READ", "WRITE", "MANAGE"}
        violations = []

        for filepath, content in load_all_tf_content():
            matches = re.findall(
                r'permission\s*=\s*"([^"]+)"',
                content
            )
            for perm in matches:
                if perm.upper() not in valid_permissions:
                    violations.append(
                        f"FAIL  [{filepath}] Invalid secret ACL permission: '{perm}'\n"
                        f"      Valid values: READ, WRITE, MANAGE"
                    )

        assert not violations, "\n\n🚨 INVALID SECRET ACL PERMISSIONS:\n\n" + "\n".join(violations)

    def test_non_admin_groups_cannot_manage_secret_scopes(self):
        """Only admin groups can hold MANAGE permission on secret scopes."""
        admin_groups = {"admins", "dbx-admins", "platform_engineers"}
        violations = []

        for filepath, content in load_all_tf_content():
            # Look for { principal = "X", permission = "MANAGE" } patterns
            # Use a pattern that finds principal and permission on adjacent lines
            manage_grants = re.findall(
                r'principal\s*=\s*"([^"]+)"[^}]*?permission\s*=\s*"MANAGE"',
                content, re.DOTALL
            )
            for principal in manage_grants:
                # Skip service principals (GUIDs) and admin groups
                if principal in admin_groups:
                    continue
                if re.match(r'[0-9a-f]{8}-[0-9a-f]{4}', principal):
                    continue  # Service principal UUID
                violations.append(
                    f"FAIL  [{filepath}]\n"
                    f"      '{principal}' has MANAGE on a secret scope.\n"
                    f"      Only admin groups may MANAGE secret scopes."
                )

        assert not violations, "\n\n🚨 NON-ADMIN MANAGING SECRET SCOPES:\n\n" + "\n".join(violations)
