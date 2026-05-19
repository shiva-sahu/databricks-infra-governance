# terraform/modules/sql-warehouse/variables.tf

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, prod)."
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "cost_centre" {
  type        = string
  description = "Billing code for the SQL warehouses in this environment."
  validation {
    condition     = can(regex("^CC-[0-9]{4}$", var.cost_centre))
    error_message = "cost_centre must be in CC-XXXX format (e.g. CC-1001)."
  }
}

# ── Analyst Warehouse ──────────────────────────────────────────────────────────

variable "analyst_cluster_size" {
  type        = string
  description = "DBU size for the analyst warehouse. Small size keeps costs predictable for BI queries."
  default     = "2X-Small"
  validation {
    condition     = contains(["2X-Small", "X-Small", "Small", "Medium", "Large"], var.analyst_cluster_size)
    error_message = "analyst_cluster_size must be a valid Databricks warehouse size."
  }
}

variable "analyst_max_clusters" {
  type        = number
  description = "Maximum concurrent clusters for the analyst warehouse (scale-out limit)."
  default     = 2
  validation {
    condition     = var.analyst_max_clusters >= 1 && var.analyst_max_clusters <= 10
    error_message = "analyst_max_clusters must be between 1 and 10."
  }
}

variable "analyst_auto_stop_mins" {
  type        = number
  description = "Minutes of inactivity before the analyst warehouse stops. Never set to 0."
  default     = 10
  validation {
    condition     = var.analyst_auto_stop_mins >= 1
    error_message = "analyst_auto_stop_mins must be at least 1. Setting 0 disables auto-stop — not permitted."
  }
}

variable "analyst_groups" {
  type        = list(string)
  description = "Groups that can USE the analyst warehouse."
  default     = []
}

# ── Engineer Warehouse ─────────────────────────────────────────────────────────

variable "engineer_cluster_size" {
  type        = string
  description = "DBU size for the engineering warehouse. Larger than analyst to handle ETL workloads."
  default     = "Small"
  validation {
    condition     = contains(["2X-Small", "X-Small", "Small", "Medium", "Large"], var.engineer_cluster_size)
    error_message = "engineer_cluster_size must be a valid Databricks warehouse size."
  }
}

variable "engineer_max_clusters" {
  type        = number
  description = "Maximum concurrent clusters for the engineering warehouse."
  default     = 3
  validation {
    condition     = var.engineer_max_clusters >= 1 && var.engineer_max_clusters <= 10
    error_message = "engineer_max_clusters must be between 1 and 10."
  }
}

variable "engineer_auto_stop_mins" {
  type        = number
  description = "Minutes of inactivity before the engineering warehouse stops."
  default     = 20
  validation {
    condition     = var.engineer_auto_stop_mins >= 1
    error_message = "engineer_auto_stop_mins must be at least 1."
  }
}

variable "engineer_groups" {
  type        = list(string)
  description = "Groups that can USE the engineering warehouse."
  default     = []
}
