output "endpoint" { value = local.endpoint }
output "port" { value = local.port }
output "database_name" { value = var.database_name }
output "username" { value = "blackbox" }
output "password" {
  value     = random_password.db.result
  sensitive = true
}
output "database_url" {
  description = "Full asyncpg connection string, ready for DATABASE_URL."
  value       = "postgresql+asyncpg://blackbox:${random_password.db.result}@${local.endpoint}:${local.port}/${var.database_name}"
  sensitive   = true
}
output "security_group_id" { value = aws_security_group.db.id }
