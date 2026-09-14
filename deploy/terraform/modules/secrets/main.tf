# Secrets Manager (Section 9). Only holds the Anthropic API key, and only
# when model_provider = "anthropic" — the preferred Bedrock path needs no
# secret at all, since the mediator authenticates to Bedrock via its ECS
# task role (IAM), not an API key (Section 7: "Bedrock (preferred, keeps
# traffic in-account)"). Either way, only the mediator's task role can read
# this — never the agent (I3).

variable "name_prefix" { type = string }
variable "model_provider" { type = string }
variable "anthropic_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "database_url" {
  type      = string
  sensitive = true
}

resource "aws_secretsmanager_secret" "anthropic_api_key" {
  count = var.model_provider == "anthropic" ? 1 : 0
  name  = "${var.name_prefix}/anthropic-api-key"
}

resource "aws_secretsmanager_secret_version" "anthropic_api_key" {
  count         = var.model_provider == "anthropic" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.anthropic_api_key[0].id
  secret_string = var.anthropic_api_key
}

resource "aws_secretsmanager_secret" "database_url" {
  name = "${var.name_prefix}/database-url"
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = var.database_url
}

output "anthropic_api_key_arn" {
  value = var.model_provider == "anthropic" ? aws_secretsmanager_secret.anthropic_api_key[0].arn : null
}
output "database_url_secret_arn" { value = aws_secretsmanager_secret.database_url.arn }
