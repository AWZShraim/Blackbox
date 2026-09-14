output "ecs_execution_role_arn" { value = aws_iam_role.ecs_execution.arn }
output "mediator_task_role_arn" { value = aws_iam_role.mediator_task.arn }
output "recorder_task_role_arn" { value = aws_iam_role.recorder_task.arn }
output "demo_task_role_arn" { value = aws_iam_role.demo_task.arn }
output "investigator_task_role_arn" { value = aws_iam_role.investigator_task.arn }
output "credential_broker_role_arn" { value = aws_iam_role.credential_broker.arn }
