variable "name_prefix" { type = string }
variable "engine_mode" {
  type = string
  validation {
    condition     = contains(["rds", "aurora_serverless_v2"], var.engine_mode)
    error_message = "engine_mode must be \"rds\" or \"aurora_serverless_v2\"."
  }
}
variable "database_name" { type = string }
variable "az_count_for_aurora" {
  description = "Number of Aurora reader/writer instances to provision (ignored when engine_mode = \"rds\")."
  type        = number
  default     = 2
}
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect to Postgres on 5432 (the mediator and recorder services)."
  type        = list(string)
}
