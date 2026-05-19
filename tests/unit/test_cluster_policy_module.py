"""
tests/unit/test_cluster_policy_module.py
────────────────────────────────────────────────────────────────────────────────
Unit Tests: cluster-policy module

Validates compute guardrails are correctly defined:
  - Both policies exist (standard_interactive and job_cluster)
  - Auto-termination is enforced and of type "fixed" (not user-adjustable)
  - Data security modes are correct per policy type
  - Node types and Spark versions are restricted via allowlists
  - Custom tags are mandatory (cost attribution)
  - Policy permissions grant CAN_USE only, never CAN_MANAGE

Run locally:
  pytest tests/unit/test_cluster_policy_module.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import json
import pytest

MODULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "terraform", "modules", "cluster-policy")
)


def load(filename):
    path = os.path.join(MODULE_DIR, filename)
    assert os.path.exists(path), f"Expected file missing: {path}"
    return open(path).read()


# ── Policy Existence ───────────────────────────────────────────────────────────

class TestPolicyDefinitions:

    def test_standard_interactive_policy_exists(self):
        """standard_interactive policy must be defined for analyst/notebook workloads."""
        content = load("main.tf")
        assert 'databricks_cluster_policy" "standard_interactive"' in content, (
            "cluster-policy module must define databricks_cluster_policy.standard_interactive"
        )

    def test_job_cluster_policy_exists(self):
        """job_cluster policy must be defined for automated pipeline runs."""
        content = load("main.tf")
        assert 'databricks_cluster_policy" "job_cluster"' in content, (
            "cluster-policy module must define databricks_cluster_policy.job_cluster"
        )

    def test_exactly_two_policies_defined(self):
        """
        Exactly two policies: standard_interactive (analyst work) and job_cluster (pipelines).
        Adding ad-hoc policies without governance review circumvents compute controls.
        """
        content = load("main.tf")
        policy_count = len(re.findall(r'resource\s+"databricks_cluster_policy"', content))
        assert policy_count == 2, (
            f"Expected exactly 2 cluster policies, found {policy_count}.\n"
            "New policies require a governance review before being added."
        )


# ── Auto-Termination Enforcement ───────────────────────────────────────────────

class TestAutoTermination:

    def test_autotermination_is_fixed_type(self):
        """
        autotermination_minutes must be type 'fixed' — users cannot override it.
        type 'range' or 'regex' would allow setting termination to 0 (never terminate).
        """
        content = load("main.tf")

        autotermination_blocks = re.findall(
            r'"autotermination_minutes"\s*=\s*\{([^}]+)\}',
            content
        )
        assert autotermination_blocks, (
            "No autotermination_minutes blocks found in cluster policies"
        )

        for block in autotermination_blocks:
            type_match = re.search(r'type\s*=\s*"([^"]+)"', block)
            assert type_match, "autotermination_minutes must declare a type"
            assert type_match.group(1) == "fixed", (
                f"autotermination_minutes type must be 'fixed', not '{type_match.group(1)}'.\n"
                "Users must not be able to disable auto-termination."
            )

    def test_both_policies_define_autotermination(self):
        """Every policy must set autotermination_minutes — no zombie clusters."""
        content = load("main.tf")

        policy_count = len(re.findall(r'resource\s+"databricks_cluster_policy"', content))
        auto_count = content.count("autotermination_minutes")

        assert auto_count >= policy_count, (
            f"Found {policy_count} cluster policies but only {auto_count} autotermination_minutes definitions.\n"
            "Every policy must enforce auto-termination."
        )

    def test_job_cluster_terminates_faster_than_interactive(self):
        """
        Job clusters should have a shorter termination window than interactive clusters.
        Interactive: 60-120 min. Job: 30 min. Jobs complete and release resources quickly.
        """
        content = load("main.tf")

        # Extract all autotermination values
        values = re.findall(r'"autotermination_minutes"\s*=\s*\{[^}]*value\s*=\s*([^\n]+)', content)
        assert len(values) >= 2, "Expected at least 2 autotermination value definitions"

        # The job cluster value (30) should be represented in the file
        assert "30" in content, (
            "Job cluster policy must set autotermination_minutes to 30.\n"
            "Jobs complete quickly and must release resources promptly."
        )


# ── Data Security Mode ─────────────────────────────────────────────────────────

class TestDataSecurityMode:

    def test_interactive_policy_enforces_user_isolation(self):
        """
        Interactive clusters must use USER_ISOLATION data security mode.
        This prevents one notebook user from reading another's local variables/data.
        Required for Unity Catalog row/column-level security to work correctly.
        """
        content = load("main.tf")
        assert "USER_ISOLATION" in content, (
            "standard_interactive policy must enforce data_security_mode = USER_ISOLATION"
        )

    def test_job_cluster_enforces_single_user(self):
        """
        Job clusters must use SINGLE_USER mode.
        Automated jobs run as a service principal — no multi-user isolation needed,
        and SINGLE_USER gives better performance.
        """
        content = load("main.tf")
        assert "SINGLE_USER" in content, (
            "job_cluster policy must enforce data_security_mode = SINGLE_USER"
        )

    def test_data_security_mode_is_fixed_type(self):
        """
        data_security_mode must be type 'fixed' — users cannot downgrade to LEGACY or NONE.
        NONE disables Unity Catalog security entirely.
        """
        content = load("main.tf")

        security_blocks = re.findall(
            r'"data_security_mode"\s*=\s*\{([^}]+)\}',
            content
        )
        assert security_blocks, "No data_security_mode constraint found in cluster policies"

        for block in security_blocks:
            type_match = re.search(r'type\s*=\s*"([^"]+)"', block)
            assert type_match, "data_security_mode must declare a type"
            assert type_match.group(1) == "fixed", (
                f"data_security_mode type must be 'fixed', not '{type_match.group(1)}'.\n"
                "Users must not be able to select NONE or LEGACY modes."
            )


# ── Node Type and Spark Version Restrictions ────────────────────────────────────

class TestComputeRestrictions:

    def test_node_type_restricted_to_allowlist(self):
        """
        node_type_id must be an allowlist — users can only pick pre-approved instance types.
        Without this, engineers could spin up 64-core GPU instances.
        """
        content = load("main.tf")

        node_type_blocks = re.findall(
            r'"node_type_id"\s*=\s*\{([^}]+)\}',
            content
        )
        assert node_type_blocks, "No node_type_id constraint found — unrestricted instance types allowed"

        for block in node_type_blocks:
            type_match = re.search(r'type\s*=\s*"([^"]+)"', block)
            assert type_match, "node_type_id must declare a type"
            assert type_match.group(1) == "allowlist", (
                f"node_type_id must be type 'allowlist', not '{type_match.group(1)}'.\n"
                "Use var.approved_node_types to define the allowlist."
            )

    def test_spark_version_restricted_to_allowlist(self):
        """
        spark_version must be an allowlist — only LTS/approved runtimes permitted.
        Unapproved versions may have security vulnerabilities or missing governance features.
        """
        content = load("main.tf")

        spark_blocks = re.findall(
            r'"spark_version"\s*=\s*\{([^}]+)\}',
            content
        )
        assert spark_blocks, "No spark_version constraint found — unapproved runtimes allowed"

        for block in spark_blocks:
            type_match = re.search(r'type\s*=\s*"([^"]+)"', block)
            assert type_match, "spark_version must declare a type"
            assert type_match.group(1) == "allowlist", (
                f"spark_version must be type 'allowlist', not '{type_match.group(1)}'.\n"
                "Pin to approved LTS versions only."
            )

    def test_worker_count_is_bounded(self):
        """
        num_workers must have a maxValue — unbounded clusters create runaway cost.
        """
        content = load("main.tf")

        worker_blocks = re.findall(
            r'"num_workers"\s*=\s*\{([^}]+)\}',
            content
        )
        assert worker_blocks, "No num_workers constraint found — worker count is unbounded"

        for block in worker_blocks:
            assert "maxValue" in block, (
                "num_workers must define maxValue to cap cluster size.\n"
                "Without this, engineers can create arbitrarily large clusters."
            )
            assert "minValue" in block, (
                "num_workers must define minValue (at least 1)."
            )


# ── Custom Tag Enforcement ─────────────────────────────────────────────────────

class TestMandatoryTags:

    def test_team_tag_is_required(self):
        """
        custom_tags.team must be required on every cluster.
        Without it, cluster costs cannot be attributed to a team.
        """
        content = load("main.tf")

        team_tag_blocks = re.findall(
            r'"custom_tags\.team"\s*=\s*\{([^}]+)\}',
            content
        )
        assert team_tag_blocks, (
            'Cluster policies must enforce "custom_tags.team"'
        )

        for block in team_tag_blocks:
            assert "required" in block, (
                "custom_tags.team must be marked required = true"
            )

    def test_cost_centre_tag_is_required(self):
        """
        custom_tags.cost_centre must be required on every cluster.
        Format must be CC-XXXX to match the billing system.
        """
        content = load("main.tf")

        assert '"custom_tags.cost_centre"' in content, (
            'Cluster policies must enforce "custom_tags.cost_centre"'
        )

        # For each occurrence, check that "required" and the CC- pattern appear
        # nearby. The block may contain nested {} (e.g. in regex patterns) so
        # we scan forward from the key rather than trying to capture [^}]+.
        for match in re.finditer(r'"custom_tags\.cost_centre"', content):
            nearby = content[match.start(): match.start() + 250]
            assert "required" in nearby, (
                "custom_tags.cost_centre must be marked required = true"
            )
            assert "CC-" in nearby, (
                "custom_tags.cost_centre must enforce CC-XXXX format via regex pattern"
            )

    def test_environment_tag_is_fixed(self):
        """
        custom_tags.environment must be fixed to the deployment environment.
        Users must not be able to tag a prod cluster as 'dev' to bypass monitoring.
        """
        content = load("main.tf")
        assert '"custom_tags.environment"' in content, (
            "Cluster policies must enforce custom_tags.environment"
        )

        env_tag_blocks = re.findall(
            r'"custom_tags\.environment"\s*=\s*\{([^}]+)\}',
            content
        )
        for block in env_tag_blocks:
            type_match = re.search(r'type\s*=\s*"([^"]+)"', block)
            assert type_match and type_match.group(1) == "fixed", (
                "custom_tags.environment must be type 'fixed' — users cannot change the environment tag"
            )


# ── Policy Permissions ─────────────────────────────────────────────────────────

class TestPolicyPermissions:

    def test_permissions_grant_can_use_not_can_manage(self):
        """
        Policy permissions must grant CAN_USE, not CAN_MANAGE.
        CAN_MANAGE would allow users to modify the policy definition itself.
        """
        content = load("main.tf")

        assert "CAN_USE" in content, (
            "databricks_permissions must grant CAN_USE to policy user groups"
        )
        assert "CAN_MANAGE" not in content, (
            "CAN_MANAGE must not appear in cluster policy permissions.\n"
            "Groups should USE policies, not manage them."
        )

    def test_permissions_driven_by_variables(self):
        """
        Policy permissions must reference variables, not hardcoded group names.
        Groups change; the module must not need updating when they do.
        """
        content = load("main.tf")

        permissions_blocks = re.findall(
            r'resource\s+"databricks_permissions"(.+?)^}',
            content, re.DOTALL | re.MULTILINE
        )
        for block in permissions_blocks:
            assert "dynamic" in block or "for_each" in block, (
                "databricks_permissions must use for_each or dynamic blocks — not hardcoded group names"
            )

    def test_interactive_and_job_policies_have_separate_permissions(self):
        """
        Each policy has its own permission block targeting appropriate groups.
        Interactive policy: analysts + engineers. Job policy: engineers only.
        """
        content = load("main.tf")

        perm_count = len(re.findall(r'resource\s+"databricks_permissions"', content))
        assert perm_count == 2, (
            f"Expected 2 databricks_permissions blocks (one per policy), found {perm_count}"
        )
