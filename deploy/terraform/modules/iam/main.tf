# ECS execution role (shared — pulls images, writes logs; every task needs
# it) plus per-service task roles scoped to exactly what that service does
# (least privilege). The AwsStsBroker role at the bottom is I3's "mediator
# mints short-lived scoped credentials via STS AssumeRole with a session
# policy" made real: only the mediator's task role can assume it, and the
# session policy narrowing what that assumed identity can do is applied by
# the mediator itself, per call, at AssumeRole time
# (mediator/credentials/aws_sts.py) — this role is deliberately broad here
# (a PoC default), with the *session policy* doing the real narrowing.

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "ecs_execution" {
  name = "${var.name_prefix}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${var.name_prefix}-ecs-execution-secrets"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = compact([var.database_url_secret_arn, var.anthropic_api_key_arn])
    }]
  })
}

# -- mediator task role -------------------------------------------------------

resource "aws_iam_role" "mediator_task" {
  name = "${var.name_prefix}-mediator-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "mediator_task" {
  name = "${var.name_prefix}-mediator-task-policy"
  role = aws_iam_role.mediator_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      var.model_provider == "bedrock" ? [{
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "*"
      }] : [],
      [
        {
          # I3: the mediator, and only the mediator, may assume the scoped
          # credential-broker role to mint per-call session credentials.
          Effect   = "Allow"
          Action   = ["sts:AssumeRole"]
          Resource = aws_iam_role.credential_broker.arn
        },
        {
          Effect   = "Allow"
          Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
          Resource = var.demo_sessions_table_arn
        },
      ]
    )
  })
}

# -- recorder task role ---------------------------------------------------

resource "aws_iam_role" "recorder_task" {
  name = "${var.name_prefix}-recorder-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "recorder_task" {
  name = "${var.name_prefix}-recorder-task-policy"
  role = aws_iam_role.recorder_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
      Resource = [var.archive_bucket_arn, "${var.archive_bucket_arn}/*"]
    }]
  })
}

# -- demo orchestrator task role: can launch ephemeral agent tasks --------

resource "aws_iam_role" "demo_task" {
  name = "${var.name_prefix}-demo-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "demo_task" {
  name = "${var.name_prefix}-demo-task-policy"
  role = aws_iam_role.demo_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask", "ecs:StopTask", "ecs:DescribeTasks"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.ecs_execution.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/${var.name_prefix}/*"
      },
    ]
  })
}

# -- investigator task role: read-only against the recorder over HTTP, no
#    direct AWS data access needed beyond logs (covered by the execution role)

resource "aws_iam_role" "investigator_task" {
  name = "${var.name_prefix}-investigator-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# -- credential broker role (I3 / AwsStsBroker) ------------------------------

resource "aws_iam_role" "credential_broker" {
  name = "${var.name_prefix}-credential-broker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.mediator_task.arn }
      Action    = "sts:AssumeRole"
    }]
  })
}

# PoC-default permissions for the scoped session (mediator/credentials/aws_sts.py's
# policy_for_tool() narrows this further with a per-call SESSION POLICY —
# this role's own policy is the outer bound that session policy can only
# restrict, never expand).
resource "aws_iam_role_policy" "credential_broker" {
  name = "${var.name_prefix}-credential-broker-policy"
  role = aws_iam_role.credential_broker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "s3:GetObject", "s3:PutObject"]
      Resource = "*"
    }]
  })
}
