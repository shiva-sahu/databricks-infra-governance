# terraform/modules/cluster-policy/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# Cluster Policy Module
# Enforces compute guardrails across the organisation.
# No cluster can be created that violates these policies.
# Engineers choose FROM these policies — they cannot override them.
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.35"
    }
  }
}

# ── Standard Interactive Policy ───────────────────────────────────────────────
# For analyst/notebook work. Auto-terminates. Capped at a reasonable size.
resource "databricks_cluster_policy" "standard_interactive" {
  name = "${var.environment}_standard_interactive"

  definition = jsonencode({
    # Governance: auto-termination is MANDATORY. No zombie clusters.
    "autotermination_minutes" = {
      type  = "fixed"
      value = var.environment == "prod" ? 60 : 120
    }

    # Runtime: pinned to approved LTS versions only
    "spark_version" = {
      type   = "allowlist"
      values = var.approved_spark_versions
    }

    # Compute: cap maximum workers to control cost
    "num_workers" = {
      type       = "range"
      minValue   = 1
      maxValue   = var.environment == "prod" ? 10 : 4
    }

    # Node types: only cost-efficient instance families
    "node_type_id" = {
      type   = "allowlist"
      values = var.approved_node_types
    }

    # Unity Catalog data access mode required
    "data_security_mode" = {
      type  = "fixed"
      value = "USER_ISOLATION"
    }

    # Tags: mandatory for cost attribution and governance
    "custom_tags.team" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.cost_centre" = {
      type     = "regex"
      pattern  = "^CC-[0-9]{4}$"
      required = true
    }
    "custom_tags.environment" = {
      type  = "fixed"
      value = var.environment
    }
    "custom_tags.project" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.data_classification" = {
      type     = "regex"
      pattern  = "^(public|internal|confidential|restricted)$"
      required = true
    }
  })
}

# ── Job Cluster Policy ────────────────────────────────────────────────────────
# For automated job runs. More compute headroom, stricter lifecycle.
resource "databricks_cluster_policy" "job_cluster" {
  name = "${var.environment}_job_cluster"

  definition = jsonencode({
    "autotermination_minutes" = {
      type  = "fixed"
      value = 30  # Jobs terminate shortly after completion
    }

    "spark_version" = {
      type   = "allowlist"
      values = var.approved_spark_versions
    }

    "num_workers" = {
      type       = "range"
      minValue   = 1
      maxValue   = var.environment == "prod" ? 20 : 8
    }

    "node_type_id" = {
      type   = "allowlist"
      values = var.approved_node_types
    }

    "data_security_mode" = {
      type  = "fixed"
      value = "SINGLE_USER"
    }

    "custom_tags.team" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.cost_centre" = {
      type     = "regex"
      pattern  = "^CC-[0-9]{4}$"
      required = true
    }
    "custom_tags.environment" = {
      type  = "fixed"
      value = var.environment
    }
    "custom_tags.project" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.data_classification" = {
      type     = "regex"
      pattern  = "^(public|internal|confidential|restricted)$"
      required = true
    }
  })
}

# ── ML / Data Science Policy ──────────────────────────────────────────────────
# For model training and experimentation. GPU-capable. Single-user isolation.
resource "databricks_cluster_policy" "ml_interactive" {
  name = "${var.environment}_ml_interactive"

  definition = jsonencode({
    "autotermination_minutes" = {
      type  = "fixed"
      value = var.environment == "prod" ? 60 : 180
    }

    "spark_version" = {
      type   = "allowlist"
      values = var.approved_ml_spark_versions
    }

    "num_workers" = {
      type     = "range"
      minValue = 1
      maxValue = var.environment == "prod" ? 8 : 4
    }

    "node_type_id" = {
      type   = "allowlist"
      values = var.approved_ml_node_types
    }

    # ML workloads run single-user for model training isolation
    "data_security_mode" = {
      type  = "fixed"
      value = "SINGLE_USER"
    }

    "custom_tags.team" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.cost_centre" = {
      type     = "regex"
      pattern  = "^CC-[0-9]{4}$"
      required = true
    }
    "custom_tags.environment" = {
      type  = "fixed"
      value = var.environment
    }
    "custom_tags.project" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.data_classification" = {
      type     = "regex"
      pattern  = "^(public|internal|confidential|restricted)$"
      required = true
    }
  })
}

# ── High-Memory Policy ────────────────────────────────────────────────────────
# For large dataset processing requiring memory-optimised VMs.
resource "databricks_cluster_policy" "high_memory" {
  name = "${var.environment}_high_memory"

  definition = jsonencode({
    "autotermination_minutes" = {
      type  = "fixed"
      value = var.environment == "prod" ? 60 : 120
    }

    "spark_version" = {
      type   = "allowlist"
      values = var.approved_spark_versions
    }

    "num_workers" = {
      type     = "range"
      minValue = 2
      maxValue = var.environment == "prod" ? 8 : 4
    }

    "node_type_id" = {
      type   = "allowlist"
      values = var.approved_high_memory_node_types
    }

    "data_security_mode" = {
      type  = "fixed"
      value = "USER_ISOLATION"
    }

    "custom_tags.team" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.cost_centre" = {
      type     = "regex"
      pattern  = "^CC-[0-9]{4}$"
      required = true
    }
    "custom_tags.environment" = {
      type  = "fixed"
      value = var.environment
    }
    "custom_tags.project" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.data_classification" = {
      type     = "regex"
      pattern  = "^(public|internal|confidential|restricted)$"
      required = true
    }
  })
}

# ── Single-User Policy ────────────────────────────────────────────────────────
# Lightweight policy for personal development clusters. Strict size limits.
resource "databricks_cluster_policy" "single_user" {
  name = "${var.environment}_single_user"

  definition = jsonencode({
    "autotermination_minutes" = {
      type  = "fixed"
      value = var.environment == "prod" ? 30 : 60
    }

    "spark_version" = {
      type   = "allowlist"
      values = var.approved_spark_versions
    }

    "num_workers" = {
      type     = "range"
      minValue = 0
      maxValue = var.environment == "prod" ? 4 : 2
    }

    "node_type_id" = {
      type   = "allowlist"
      values = var.approved_node_types
    }

    "data_security_mode" = {
      type  = "fixed"
      value = "SINGLE_USER"
    }

    "custom_tags.team" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.cost_centre" = {
      type     = "regex"
      pattern  = "^CC-[0-9]{4}$"
      required = true
    }
    "custom_tags.environment" = {
      type  = "fixed"
      value = var.environment
    }
    "custom_tags.project" = {
      type     = "regex"
      pattern  = ".+"
      required = true
    }
    "custom_tags.data_classification" = {
      type     = "regex"
      pattern  = "^(public|internal|confidential|restricted)$"
      required = true
    }
  })
}

# ── Policy Permissions ────────────────────────────────────────────────────────
# Who can USE each policy — controlled, not open
resource "databricks_permissions" "standard_interactive_policy" {
  cluster_policy_id = databricks_cluster_policy.standard_interactive.id

  dynamic "access_control" {
    for_each = var.interactive_policy_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}

resource "databricks_permissions" "job_cluster_policy" {
  cluster_policy_id = databricks_cluster_policy.job_cluster.id

  dynamic "access_control" {
    for_each = var.job_policy_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}

resource "databricks_permissions" "ml_interactive_policy" {
  cluster_policy_id = databricks_cluster_policy.ml_interactive.id

  dynamic "access_control" {
    for_each = var.ml_policy_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}

resource "databricks_permissions" "high_memory_policy" {
  cluster_policy_id = databricks_cluster_policy.high_memory.id

  dynamic "access_control" {
    for_each = var.high_memory_policy_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}

resource "databricks_permissions" "single_user_policy" {
  cluster_policy_id = databricks_cluster_policy.single_user.id

  dynamic "access_control" {
    for_each = var.single_user_policy_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}
