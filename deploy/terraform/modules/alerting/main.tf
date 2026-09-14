# Hard AWS Budgets alarm at $25/month with SNS notification (required in
# every profile), plus the automated kill switch (Section 8) that flips an
# SSM parameter the demo service polls when the budget alarm fires.

data "aws_caller_identity" "current" {}

resource "aws_sns_topic" "budget_alerts" {
  name = "${var.name_prefix}-budget-alerts"
}

resource "aws_sns_topic_policy" "budget_alerts" {
  arn = aws_sns_topic.budget_alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowBudgetsPublish"
      Effect    = "Allow"
      Principal = { Service = "budgets.amazonaws.com" }
      Action    = "SNS:Publish"
      Resource  = aws_sns_topic.budget_alerts.arn
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.budget_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "email"
  endpoint  = var.budget_alert_email
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name = "TagKeyValue"
    values = [
      "user:Project$blackbox",
    ]
  }

  # Two rungs: an early warning at 80% actual spend (still gives a human a
  # chance to look before anything gets disabled), and the kill switch
  # itself at 100% forecasted spend (predictive, so it fires before the
  # month is actually over budget, not after).
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
  }
}

# -- kill switch: SSM parameter + Lambda -------------------------------------

resource "aws_ssm_parameter" "kill_switch" {
  name        = "/${var.name_prefix}/demo/live_runs_enabled"
  type        = "String"
  value       = "true" # operator resets this to "true" manually after investigating the spend
  description = "Polled by scenarios/demo/guardrails.py's KillSwitch. Flipped to \"false\" automatically by the budget-alarm Lambda."

  lifecycle {
    # Terraform must not fight the Lambda over this value between applies.
    ignore_changes = [value]
  }
}

data "archive_file" "kill_switch_lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda_src/kill_switch.py"
  output_path = "${path.module}/lambda_src/kill_switch.zip"
}

resource "aws_iam_role" "kill_switch_lambda" {
  name = "${var.name_prefix}-kill-switch-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "kill_switch_lambda" {
  name = "${var.name_prefix}-kill-switch-lambda-policy"
  role = aws_iam_role.kill_switch_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:PutParameter"]
        Resource = aws_ssm_parameter.kill_switch.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:*"
      },
    ]
  })
}

resource "aws_lambda_function" "kill_switch" {
  function_name    = "${var.name_prefix}-kill-switch"
  role             = aws_iam_role.kill_switch_lambda.arn
  handler          = "kill_switch.handler"
  runtime          = "python3.12"
  timeout          = 10
  filename         = data.archive_file.kill_switch_lambda.output_path
  source_code_hash = data.archive_file.kill_switch_lambda.output_base64sha256

  environment {
    variables = {
      KILL_SWITCH_PARAM_NAME = aws_ssm_parameter.kill_switch.name
    }
  }
  tags = { Name = "${var.name_prefix}-kill-switch" }
}

resource "aws_lambda_permission" "allow_sns" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kill_switch.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.budget_alerts.arn
}

resource "aws_sns_topic_subscription" "kill_switch_lambda" {
  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.kill_switch.arn
}
