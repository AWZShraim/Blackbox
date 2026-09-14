variable "name_prefix" { type = string }
variable "database_url_secret_arn" { type = string }
variable "anthropic_api_key_arn" {
  type    = string
  default = null
}
variable "archive_bucket_arn" { type = string }
variable "demo_sessions_table_arn" { type = string }
variable "model_provider" { type = string }
