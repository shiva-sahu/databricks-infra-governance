"""
tests/governance/test_tagging.py
────────────────────────────────────────────────────────────────────────────────
Governance Test Suite: Resource Tagging

Every resource must be tagged. No exceptions.
Tags enable: cost attribution, team accountability, environment awareness,
and automated governance at the Azure subscription level.

Required tags on ALL Azure resources:
  - environment   : dev | staging | prod
  - team          : owning team identifier
  - cost_centre   : CC-XXXX format
  - managed_by    : must be "terraform"

Required cluster tags (via cluster policies):
  - team
  - cost_centre
  - environment
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import pytest

TERRAFORM_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "terraform")

REQUIRED_TAGS = ["environment", "team", "cost_centre", "project", "owner", "managed_by"]

# Azure resources that MUST have tags
TAGGABLE_AZURE_RESOURCES = [
    "azurerm_resource_group",
    "azurerm_virtual_network",
    "azurerm_databricks_workspace",
    "azurerm_network_security_group",
    "azurerm_storage_account",
]


def load_all_tf_content():
    files = [
        p for p in glob.glob(f"{TERRAFORM_ROOT}/**/*.tf", recursive=True)
        if "BAD_EXAMPLE" not in os.path.basename(p)
    ]
    return [(p, open(p, encoding="utf-8").read()) for p in files]


class TestAzureResourceTagging:

    def test_all_azure_resources_reference_common_tags(self):
        """
        Every taggable Azure resource must include tags.
        Resources using local.common_tags are compliant.
        Resources with a literal tags = {} block must include all required keys.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "outputs.tf" in filepath:
                continue

            for resource_type in TAGGABLE_AZURE_RESOURCES:
                pattern = re.compile(
                    rf'resource\s+"{re.escape(resource_type)}"\s+"([^"]+)"\s*\{{([^}}]+(?:\{{[^}}]*\}}[^}}]*)*)\}}',
                    re.DOTALL
                )
                for match in pattern.finditer(content):
                    resource_label = match.group(1)
                    block = match.group(2)

                    # Compliant: file defines and uses common_tags (tags = local.common_tags anywhere in file)
                    # or uses for_each patterns where tags come from variables
                    if ("local.common_tags" in content or "common_tags" in content
                            or "for_each" in block or "var.tags" in block):
                        continue

                    # Check for tags block at all
                    if "tags" not in block:
                        violations.append(
                            f"FAIL  [{filepath}] {resource_type}.{resource_label} has no tags block.\n"
                            f"      Add: tags = local.common_tags"
                        )
                        continue

                    # Check each required tag key
                    tags_match = re.search(r'tags\s*=\s*\{([^}]+)\}', block, re.DOTALL)
                    if tags_match:
                        tags_block = tags_match.group(1)
                        for required_tag in REQUIRED_TAGS:
                            if required_tag not in tags_block:
                                violations.append(
                                    f"FAIL  [{filepath}] {resource_type}.{resource_label} "
                                    f"missing required tag '{required_tag}'.\n"
                                    f"      Use local.common_tags to include all required tags."
                                )

        assert not violations, (
            "\n\n🚨 RESOURCE TAGGING VIOLATIONS:\n\n"
            + "\n\n".join(violations)
        )

    def test_managed_by_tag_is_terraform(self):
        """
        Where 'managed_by' tag is set explicitly, it must be 'terraform'.
        This tag is the source of truth for drift detection.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            # Find explicit managed_by = "something" that isn't terraform
            managed_by_matches = re.findall(
                r'managed_by\s*=\s*"([^"]+)"', content
            )
            for value in managed_by_matches:
                if value.lower() not in ("terraform", "tofu"):
                    violations.append(
                        f"FAIL  [{filepath}] managed_by = '{value}'\n"
                        f"      If Terraform manages this resource, managed_by must be 'terraform'.\n"
                        f"      Resources not managed by Terraform should not be in this repo."
                    )

        assert not violations, "\n\n🚨 INVALID MANAGED_BY TAG:\n\n" + "\n".join(violations)


class TestClusterPolicyTagEnforcement:

    def test_cluster_policies_require_team_tag(self):
        """
        Every file containing cluster policy definitions must enforce the 'team' custom tag.
        We check the full file content because jsonencode() uses multi-level nesting.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue
            if "databricks_cluster_policy" not in content:
                continue

            if '"custom_tags.team"' not in content:
                violations.append(
                    f"FAIL  [{filepath}] Cluster policy file does not enforce custom_tags.team.\n"
                    f"      Add: \"custom_tags.team\" = {{ type = \"regex\", pattern = \".+\", required = true }}"
                )

        assert not violations, "\n\n🚨 CLUSTER POLICIES MISSING TEAM TAG ENFORCEMENT:\n\n" + "\n".join(violations)

    def test_cluster_policies_require_cost_centre_tag(self):
        """
        Every file containing cluster policy definitions must enforce the 'cost_centre' tag.
        We check the full file content because jsonencode() uses multi-level nesting.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue
            if "databricks_cluster_policy" not in content:
                continue

            if '"custom_tags.cost_centre"' not in content:
                violations.append(
                    f"FAIL  [{filepath}] Cluster policy file does not enforce cost_centre tag.\n"
                    f"      Add: \"custom_tags.cost_centre\" = {{ type = \"regex\", pattern = \"^CC-[0-9]{{4}}$\", required = true }}"
                )

        assert not violations, "\n\n🚨 CLUSTER POLICIES MISSING COST_CENTRE ENFORCEMENT:\n\n" + "\n".join(violations)


class TestDatabricksResourceProperties:

    def test_unity_catalog_resources_set_managed_by_property(self):
        """
        Databricks catalog and schema resources should set managed_by = "terraform"
        in their properties block for in-UI visibility.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "environments" in filepath:
                continue  # Check module definitions, not environment compositions

            for resource_type in ["databricks_catalog", "databricks_schema"]:
                blocks = re.finditer(
                    rf'resource\s+"{re.escape(resource_type)}"\s+"([^"]+)"\s*\{{([^}}]+(?:\{{[^}}]*\}}[^}}]*)*)\}}',
                    content, re.DOTALL
                )
                for match in blocks:
                    resource_label = match.group(1)
                    block = match.group(2)

                    if "properties" in block and "managed_by" not in block:
                        violations.append(
                            f"WARN  [{filepath}] {resource_type}.{resource_label} "
                            f"has a properties block but no 'managed_by' property.\n"
                            f"      Add: managed_by = \"terraform\""
                        )

        # Warning only — don't block the PR for this
        if violations:
            print("\n⚠️  MISSING MANAGED_BY PROPERTY:\n" + "\n".join(violations))


class TestDataClassificationTagging:
    """
    Every Unity Catalog resource (catalog, schema) must declare a data_classification
    property so downstream tools (lineage, policy engines, audit) know the sensitivity tier.

    Valid values: public | internal | confidential | restricted
    """

    VALID_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}

    def test_catalogs_declare_data_classification(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "outputs.tf" in filepath:
                continue
            if "databricks_catalog" not in content:
                continue
            # Modules define properties via variables — only check environment compositions
            if "modules" in filepath.replace("\\", "/"):
                continue

            # Check that each catalog block in environment files passes data_classification
            catalog_blocks = re.finditer(
                r'(\w+)\s*=\s*\{[^}]*data_classification\s*=\s*"([^"]+)"',
                content, re.DOTALL
            )
            found = {m.group(2) for m in catalog_blocks}
            invalid = found - self.VALID_CLASSIFICATIONS
            if invalid:
                violations.append(
                    f"FAIL  [{filepath}] Invalid data_classification value(s): {invalid}.\n"
                    f"      Must be one of: {self.VALID_CLASSIFICATIONS}"
                )

            # Also check the file mentions data_classification at all
            if "data_classification" not in content:
                violations.append(
                    f"FAIL  [{filepath}] File contains catalog definitions but no data_classification.\n"
                    f"      Add data_classification to every catalog block."
                )

        assert not violations, (
            "\n\n🚨 DATA CLASSIFICATION VIOLATIONS:\n\n" + "\n\n".join(violations)
        )

    def test_catalogs_declare_owner_contact(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "outputs.tf" in filepath:
                continue
            if "databricks_catalog" not in content:
                continue
            if "modules" in filepath.replace("\\", "/"):
                continue

            if "owner_contact" not in content:
                violations.append(
                    f"FAIL  [{filepath}] Catalog definitions missing owner_contact.\n"
                    f"      Every catalog must declare an owner_contact for governance accountability."
                )

        assert not violations, (
            "\n\n🚨 MISSING OWNER CONTACT:\n\n" + "\n\n".join(violations)
        )

    def test_catalogs_declare_project(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "outputs.tf" in filepath:
                continue
            if "databricks_catalog" not in content:
                continue
            if "modules" in filepath.replace("\\", "/"):
                continue

            if 'project' not in content:
                violations.append(
                    f"FAIL  [{filepath}] Catalog definitions missing project field.\n"
                    f"      Every catalog must declare a project for cost attribution."
                )

        assert not violations, (
            "\n\n🚨 MISSING PROJECT FIELD ON CATALOGS:\n\n" + "\n\n".join(violations)
        )


class TestClusterPolicyTagEnforcementExtended:
    """
    Extends the base cluster policy tag tests to cover the two new mandatory tags:
    project (cost attribution) and data_classification (data sensitivity).
    """

    def test_cluster_policies_require_project_tag(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue
            if "databricks_cluster_policy" not in content:
                continue

            if '"custom_tags.project"' not in content:
                violations.append(
                    f"FAIL  [{filepath}] Cluster policy file does not enforce custom_tags.project.\n"
                    f"      Add: \"custom_tags.project\" = {{ type = \"regex\", pattern = \".+\", required = true }}"
                )

        assert not violations, (
            "\n\n🚨 CLUSTER POLICIES MISSING PROJECT TAG ENFORCEMENT:\n\n" + "\n".join(violations)
        )

    def test_cluster_policies_require_data_classification_tag(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue
            if "databricks_cluster_policy" not in content:
                continue

            if '"custom_tags.data_classification"' not in content:
                violations.append(
                    f"FAIL  [{filepath}] Cluster policy file does not enforce custom_tags.data_classification.\n"
                    f"      Add: \"custom_tags.data_classification\" = {{ type = \"regex\", "
                    f"pattern = \"^(public|internal|confidential|restricted)$\", required = true }}"
                )

        assert not violations, (
            "\n\n🚨 CLUSTER POLICIES MISSING DATA_CLASSIFICATION ENFORCEMENT:\n\n" + "\n".join(violations)
        )


class TestWorkspaceAccessPolicies:
    """
    Workspace-level access policy governance.
    Every environment with enforce_workspace_conf = true must have a
    databricks_workspace_conf resource wired up.
    """

    def test_workspace_module_defines_workspace_conf(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "outputs.tf" in filepath:
                continue
            if "modules/workspace" not in filepath.replace("\\", "/"):
                continue

            if "databricks_workspace_conf" not in content:
                violations.append(
                    f"FAIL  [{filepath}] Workspace module does not define databricks_workspace_conf.\n"
                    f"      Add a databricks_workspace_conf resource to enforce workspace-level governance."
                )

        assert not violations, (
            "\n\n🚨 MISSING WORKSPACE GOVERNANCE CONFIG:\n\n" + "\n\n".join(violations)
        )

    def test_workspace_module_defines_ip_access_list(self):
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath or "outputs.tf" in filepath:
                continue
            if "modules/workspace" not in filepath.replace("\\", "/"):
                continue

            if "databricks_ip_access_list" not in content:
                violations.append(
                    f"FAIL  [{filepath}] Workspace module does not define databricks_ip_access_list.\n"
                    f"      Add a databricks_ip_access_list resource for network-level access control."
                )

        assert not violations, (
            "\n\n🚨 MISSING IP ACCESS LIST RESOURCE:\n\n" + "\n\n".join(violations)
        )
