# Every knob below is set explicitly per profile in envs/*.tfvars — there
# is no "if profile == demo" branching anywhere in this stack. A profile is
# just a named bundle of these values; modules only ever look at the
# specific variable they need.

variable "profile_name" {
  description = "Human label for this deployment (\"demo\" or \"reference\") — used only for tags/naming, not for branching logic."
  type        = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "blackbox"
}

# -- network --------------------------------------------------------------

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "az_count" {
  description = "Demo: 1 (single AZ, minimal footprint). Reference: 3 (multi-AZ)."
  type        = number
}

variable "enable_privatelink" {
  description = "Reference only: VPC interface endpoints for ECR/S3/Secrets Manager/CloudWatch Logs/STS/Bedrock, so the always-on services need no internet egress at all. Costs ~$7-10/mo per endpoint, which is why the demo profile skips it and uses public-subnet-with-public-IP services instead."
  type        = bool
}

# -- compute ----------------------------------------------------------------

variable "use_fargate_spot" {
  description = "Demo: true (cheaper, acceptable for a non-critical public demo). Reference: false (on-demand, no capacity-interruption risk for a documented production topology)."
  type        = bool
}

variable "mediator_image" {
  description = "Container image for the mediator service (built from deploy/docker/backend.Dockerfile)."
  type        = string
}

variable "recorder_image" {
  type = string
}

variable "demo_image" {
  type = string
}

variable "investigator_image" {
  description = "Container image for the Investigator (built from investigator/Dockerfile)."
  type        = string
}

# -- database -----------------------------------------------------------

variable "database_engine_mode" {
  description = "\"rds\" (demo: db.t4g.micro, single instance) or \"aurora_serverless_v2\" (reference: multi-AZ Aurora Serverless v2 Postgres)."
  type        = string
  validation {
    condition     = contains(["rds", "aurora_serverless_v2"], var.database_engine_mode)
    error_message = "database_engine_mode must be \"rds\" or \"aurora_serverless_v2\"."
  }
}

variable "database_name" {
  type    = string
  default = "blackbox"
}

# -- storage (S3 archive, Object Lock) -------------------------------------

variable "archive_object_lock_mode" {
  description = "GOVERNANCE (demo — bypassable by an authorized admin, so `make destroy` can actually empty the bucket) or COMPLIANCE (reference — nobody, including root, can shorten or remove the lock before it expires; the spec-correct posture for a real deployment, but incompatible with an exercise that tears itself down)."
  type        = string
  validation {
    condition     = contains(["GOVERNANCE", "COMPLIANCE"], var.archive_object_lock_mode)
    error_message = "archive_object_lock_mode must be GOVERNANCE or COMPLIANCE."
  }
}

variable "archive_object_lock_retention_days" {
  type = number
}

# -- auth -------------------------------------------------------------------

variable "enable_cognito_console_auth" {
  description = "Reference: true — the Investigator sits behind Cognito, as a real deployment's forensics tool should. Demo: false — the whole point of the public demo is that a cold visitor doesn't sign up (Section 8)."
  type        = bool
}

# -- budget -------------------------------------------------------------------

variable "monthly_budget_usd" {
  description = "Hard AWS Budgets alarm threshold. Required in every profile per Section 8's abuse guardrails, extended here to the whole stack rather than just the demo's live-run kill switch."
  type        = number
  default     = 25
}

variable "budget_alert_email" {
  description = "Email address for the SNS budget-alarm subscription. Left blank to skip the subscription (the budget + alarm still exist; you just won't get notified without setting this)."
  type        = string
  default     = ""
}

# -- secrets ------------------------------------------------------------------

variable "model_provider" {
  description = "\"bedrock\" (preferred — keeps model traffic in-account, Section 7) or \"anthropic\" (direct API, needs anthropic_api_key)."
  type        = string
  default     = "bedrock"
}

variable "anthropic_api_key" {
  description = "Only used when model_provider = \"anthropic\". Left empty for bedrock. Marked sensitive so it never appears in plan/apply output."
  type        = string
  default     = ""
  sensitive   = true
}
