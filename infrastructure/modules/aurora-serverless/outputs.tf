output "cluster_arn" {
  description = "ARN of the Aurora Serverless v2 cluster."
  value       = aws_rds_cluster.this.arn
}

output "cluster_identifier" {
  description = "AWS cluster identifier (DB cluster name)."
  value       = aws_rds_cluster.this.cluster_identifier
}

output "cluster_endpoint" {
  description = "Writer endpoint hostname. App connections target this; readers go to `cluster_reader_endpoint`."
  value       = aws_rds_cluster.this.endpoint
}

output "cluster_reader_endpoint" {
  description = "Reader endpoint hostname (load-balanced across reader replicas). With a single writer instance + no readers, this resolves to the writer but the endpoint shape is preserved for future scale-out."
  value       = aws_rds_cluster.this.reader_endpoint
}

output "cluster_resource_id" {
  description = "Stable DB cluster resource id (`cluster-XXXX...`). Used to construct the `rds-db:connect` IAM policy resource ARN — `arn:aws:rds-db:{region}:{account}:dbuser:{cluster_resource_id}/{app_db_user}`."
  value       = aws_rds_cluster.this.cluster_resource_id
}

output "port" {
  description = "Cluster port (5432 for PostgreSQL)."
  value       = aws_rds_cluster.this.port
}

output "database_name" {
  description = "Initial database name (passed through from `var.database_name`)."
  value       = var.database_name
}

output "app_db_user" {
  description = "PostgreSQL role mapped to IAM auth (passed through from `var.app_db_user`)."
  value       = var.app_db_user
}

output "secret_arn" {
  description = "ARN of the break-glass master credentials in Secrets Manager. NOT used by app traffic."
  value       = aws_secretsmanager_secret.master.arn
}

output "security_group_id" {
  description = "ID of the cluster security group. Useful for cross-module diagnostics; ingress rules already attach the runtime SGs via `var.consumer_security_group_ids`."
  value       = aws_security_group.cluster.id
}

output "db_instance_arn" {
  description = "ARN of the writer instance (Performance Insights references this)."
  value       = aws_rds_cluster_instance.writer.arn
}
