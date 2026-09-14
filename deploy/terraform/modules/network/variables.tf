variable "name_prefix" { type = string }
variable "vpc_cidr" { type = string }
variable "az_count" { type = number }

variable "enable_privatelink" {
  description = "Create VPC interface endpoints (ECR, S3 gateway, Secrets Manager, CloudWatch Logs, STS, Bedrock) so services need no internet egress at all."
  type        = bool
}
