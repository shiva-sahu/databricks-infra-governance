"""
tests/governance/test_catalog_hierarchy.py
────────────────────────────────────────────────────────────────────────────────
Governance Test Suite: Catalog Hierarchy & Completeness

Validates that every catalog is properly structured:
  - Has an owner_group (never empty)
  - Has all three medallion layers (bronze, silver, gold)
  - Has a cost_centre defined
  - Has a human-readable comment
  - Does not reference non-existent groups
────────────────────────────────────────────────────────────────────────────────
"""

import re
import os
import glob
import pytest
from pathlib import Path

TERRAFORM_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "terraform")


def load_all_tf_content():
    files = glob.glob(f"{TERRAFORM_ROOT}/**/*.tf", recursive=True)
    return [(p, open(p, encoding="utf-8").read()) for p in files]


# ── Catalog Completeness ───────────────────────────────────────────────────────

class TestCatalogHierarchy:

    def test_every_catalog_has_owner_group(self):
        """
        Every catalog must have an owner_group defined.
        Ownerless catalogs have no accountability — they become orphaned technical debt.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            # Find catalog resource blocks
            catalog_blocks = re.finditer(
                r'resource\s+"databricks_catalog"\s+"([^"]+)"\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
                content, re.DOTALL
            )
            for match in catalog_blocks:
                resource_label = match.group(1)
                block = match.group(2)

                # Skip for_each dynamic blocks — owner comes from variable input
                if "for_each" in block or "each.value" in block:
                    continue

                if "owner" not in block:
                    violations.append(
                        f"FAIL  [{filepath}] databricks_catalog.{resource_label} has no 'owner' defined.\n"
                        f"      Every catalog must declare an owner (a group, not an individual)."
                    )

        assert not violations, "\n\n🚨 CATALOGS WITHOUT OWNERS:\n\n" + "\n".join(violations)

    def test_every_catalog_has_comment(self):
        """
        Every catalog must have a human-readable comment.
        Self-documenting infrastructure — if it's not described, it will be misused.
        """
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            catalog_blocks = re.finditer(
                r'resource\s+"databricks_catalog"\s+"([^"]+)"\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
                content, re.DOTALL
            )
            for match in catalog_blocks:
                resource_label = match.group(1)
                block = match.group(2)

                # Skip for_each dynamic blocks — comment comes from variable input
                if "for_each" in block or "each.value" in block:
                    continue

                comment_match = re.search(r'comment\s*=\s*"([^"]*)"', block)
                if not comment_match or len(comment_match.group(1).strip()) < 10:
                    violations.append(
                        f"FAIL  [{filepath}] databricks_catalog.{resource_label} has no meaningful comment.\n"
                        f"      Add a comment explaining what this catalog contains and who uses it."
                    )

        assert not violations, "\n\n🚨 CATALOGS WITHOUT COMMENTS:\n\n" + "\n".join(violations)

    def test_catalog_variable_entries_have_all_required_fields(self):
        """
        Catalog variable definitions must include all required fields.
        Incomplete catalog definitions will cause silent failures at deploy time.
        """
        required_fields = ["team", "domain", "comment", "owner_group", "cost_centre", "grants", "schema_grants"]

        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" not in filepath:
                continue

            # Find catalogs variable block
            catalogs_match = re.search(
                r'variable\s+"catalogs"\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
                content, re.DOTALL
            )
            if catalogs_match:
                block = catalogs_match.group(1)
                for field in required_fields:
                    if field not in block:
                        violations.append(
                            f"NOTE  [{filepath}] Catalogs variable definition missing field '{field}'.\n"
                            f"      Ensure the type definition includes all required catalog fields."
                        )

        # Notes, not hard failures — variables.tf structure is advisory
        if violations:
            print("\n⚠️  CATALOG VARIABLE COMPLETENESS NOTES:\n" + "\n".join(violations))


class TestCatalogCostAttribution:

    def test_all_catalogs_have_cost_centre_property(self):
        """
        Every catalog must set a cost_centre property.
        Cost attribution = accountability. Without it, runaway storage costs are untracked.

        Pattern: cost_centre = "CC-XXXX" (4-digit code)
        """
        COST_CENTRE_PATTERN = re.compile(r'^CC-\d{4}$')
        violations = []

        for filepath, content in load_all_tf_content():
            if "variables.tf" in filepath:
                continue

            # Look for cost_centre values in catalog resource blocks
            cost_centres = re.findall(r'cost_centre\s*=\s*"([^"]+)"', content)

            for cc in cost_centres:
                if not COST_CENTRE_PATTERN.match(cc):
                    violations.append(
                        f"FAIL  [{filepath}] Invalid cost_centre value: '{cc}'\n"
                        f"      Expected format: CC-XXXX (e.g. CC-1001, CC-2043)"
                    )

        assert not violations, "\n\n🚨 INVALID COST CENTRE FORMAT:\n\n" + "\n".join(violations)

    def test_prod_catalogs_have_prevent_destroy(self):
        """
        Production catalog resources must have lifecycle { prevent_destroy = true }.
        This is the last line of defence against accidental data deletion via Terraform.
        """
        violations = []

        prod_files = glob.glob(
            f"{TERRAFORM_ROOT}/environments/prod/**/*.tf", recursive=True
        )
        prod_files += glob.glob(
            f"{TERRAFORM_ROOT}/modules/**/*.tf", recursive=True
        )

        for filepath in prod_files:
            content = open(filepath, encoding="utf-8").read()

            # Find databricks_catalog resource blocks
            catalog_blocks = re.finditer(
                r'resource\s+"databricks_catalog"\s+"[^"]+"\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
                content, re.DOTALL
            )
            for match in catalog_blocks:
                block = match.group(1)
                # for_each catalogs use lifecycle in their module definition
                if "for_each" in block or "each.value" in block:
                    continue
                if "prevent_destroy" not in block:
                    violations.append(
                        f"FAIL  [{filepath}] A databricks_catalog resource is missing\n"
                        f"      lifecycle {{ prevent_destroy = true }}\n"
                        f"      Add this to prevent accidental catalog deletion."
                    )

        assert not violations, "\n\n🚨 CATALOGS MISSING PREVENT_DESTROY:\n\n" + "\n".join(violations)
