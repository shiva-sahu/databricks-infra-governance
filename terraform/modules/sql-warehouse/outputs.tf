# terraform/modules/sql-warehouse/outputs.tf

output "analyst_warehouse_id" {
  description = "ID of the analyst SQL warehouse."
  value       = databricks_sql_endpoint.analyst.id
}

output "analyst_warehouse_name" {
  description = "Name of the analyst SQL warehouse."
  value       = databricks_sql_endpoint.analyst.name
}

output "analyst_warehouse_jdbc_url" {
  description = "JDBC connection URL for the analyst warehouse."
  value       = databricks_sql_endpoint.analyst.jdbc_url
}

output "engineer_warehouse_id" {
  description = "ID of the engineering SQL warehouse."
  value       = databricks_sql_endpoint.engineer.id
}

output "engineer_warehouse_name" {
  description = "Name of the engineering SQL warehouse."
  value       = databricks_sql_endpoint.engineer.name
}

output "engineer_warehouse_jdbc_url" {
  description = "JDBC connection URL for the engineering warehouse."
  value       = databricks_sql_endpoint.engineer.jdbc_url
}
