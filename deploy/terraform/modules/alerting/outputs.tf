output "sns_topic_arn" { value = aws_sns_topic.budget_alerts.arn }
output "kill_switch_param_name" { value = aws_ssm_parameter.kill_switch.name }
