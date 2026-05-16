# terraform/modules/cluster-policy/variables.tf

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "approved_spark_versions" {
  description = "Allowlist of approved Databricks Runtime versions."
  type        = list(string)
  default = [
    "14.3.x-scala2.12",   # LTS
    "15.4.x-scala2.12",   # Current LTS
    "15.4.x-ml-scala2.12" # ML LTS
  ]
}

variable "approved_node_types" {
  description = "Allowlist of approved Azure VM types for cluster nodes."
  type        = list(string)
  default = [
    "Standard_DS3_v2",
    "Standard_DS4_v2",
    "Standard_E8ds_v5",
    "Standard_E16ds_v5"
  ]
}

variable "interactive_policy_groups" {
  description = "Databricks groups that can use the interactive cluster policy."
  type        = list(string)
  default     = ["data_analysts", "data_engineers", "data_scientists"]
}

variable "job_policy_groups" {
  description = "Databricks groups that can use the job cluster policy."
  type        = list(string)
  default     = ["data_engineers", "pipeline_service_principals"]
}
