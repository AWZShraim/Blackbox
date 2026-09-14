variable "name_prefix" { type = string }
variable "service_name" { type = string } # e.g. "mediator" — used for naming only
variable "cluster_id" { type = string }
variable "image" { type = string }
variable "container_port" { type = number }
variable "cpu" {
  type    = number
  default = 256
}
variable "memory" {
  type    = number
  default = 512
}
variable "desired_count" {
  type    = number
  default = 1
}
variable "use_fargate_spot" { type = bool }

variable "task_role_arn" { type = string }
variable "execution_role_arn" { type = string }

variable "subnet_ids" { type = list(string) }
variable "assign_public_ip" { type = bool }
variable "additional_ingress_security_group_ids" {
  description = "Extra security groups allowed to reach container_port, beyond the VPC CIDR (e.g. the ALB's SG for the investigator service)."
  type        = list(string)
  default     = []
}

variable "environment" {
  description = "Plain (non-secret) env vars."
  type        = map(string)
  default     = {}
}
variable "secrets" {
  description = "Env var name -> Secrets Manager ARN, injected via ECS's native secrets support (never baked into the image or task def in plaintext)."
  type        = map(string)
  default     = {}
}

variable "service_registry_arn" {
  description = "Cloud Map service ARN to register into (mediator/recorder/demo). Null for the investigator, which uses the ALB target group instead."
  type        = string
  default     = null
}
variable "target_group_arn" {
  description = "ALB target group to attach to (investigator only)."
  type        = string
  default     = null
}

variable "log_retention_days" {
  type    = number
  default = 14
}
