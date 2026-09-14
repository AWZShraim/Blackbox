output "ecr_repository_urls" {
  description = "Push images here (make tf-ecr-push) before the first apply — the task definitions reference var.*_image directly, so update envs/<profile>.tfvars with these URLs (plus a real tag) once repos exist."
  value       = module.ecr.repository_urls
}

output "investigator_url" {
  description = "Public URL of the hosted demo."
  value       = "http://${module.alb.alb_dns_name}"
}

output "database_engine" { value = var.database_engine_mode }

output "archive_bucket_name" { value = module.storage.bucket_name }

output "budget_sns_topic_arn" { value = module.alerting.sns_topic_arn }

output "estimated_monthly_cost_usd" {
  description = "See the comment at the top of envs/<profile>.tfvars for the itemized estimate this number summarizes."
  value       = var.profile_name == "demo" ? "~18-22 (see envs/demo.tfvars)" : "~340-420 (see envs/reference.tfvars, never applied)"
}
