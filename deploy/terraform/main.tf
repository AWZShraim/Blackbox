# Root module: wires every piece from Section 9's topology table together.
# Every individual knob (engine_mode, az_count, enable_privatelink, ...) is
# set per-profile in envs/*.tfvars — nothing in this file branches on a
# "profile" string; it just passes each module the variables it declared.

module "ecr" {
  source      = "./modules/ecr"
  name_prefix = var.name_prefix
}

module "network" {
  source             = "./modules/network"
  name_prefix        = var.name_prefix
  vpc_cidr           = var.vpc_cidr
  az_count           = var.az_count
  enable_privatelink = var.enable_privatelink
}

module "storage" {
  source                     = "./modules/storage"
  name_prefix                = var.name_prefix
  object_lock_mode           = var.archive_object_lock_mode
  object_lock_retention_days = var.archive_object_lock_retention_days
}

module "dynamodb" {
  source      = "./modules/dynamodb"
  name_prefix = var.name_prefix
}

module "alerting" {
  source             = "./modules/alerting"
  name_prefix        = var.name_prefix
  monthly_budget_usd = var.monthly_budget_usd
  budget_alert_email = var.budget_alert_email
}

module "cognito" {
  count       = var.enable_cognito_console_auth ? 1 : 0
  source      = "./modules/cognito"
  name_prefix = var.name_prefix
}

module "service_discovery" {
  source      = "./modules/service_discovery"
  name_prefix = var.name_prefix
  vpc_id      = module.network.vpc_id
}

module "alb" {
  source      = "./modules/alb"
  name_prefix = var.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.public_subnet_ids
}

# Populated after the mediator's ECS service (below) creates its own
# security group, since the database only accepts connections from it.
module "database" {
  source                     = "./modules/database"
  name_prefix                = var.name_prefix
  engine_mode                = var.database_engine_mode
  database_name              = var.database_name
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.database_subnet_ids
  az_count_for_aurora        = var.az_count
  allowed_security_group_ids = [module.mediator.security_group_id, module.recorder.security_group_id]
}

module "secrets" {
  source            = "./modules/secrets"
  name_prefix       = var.name_prefix
  model_provider    = var.model_provider
  anthropic_api_key = var.anthropic_api_key
  database_url      = module.database.database_url
}

module "iam" {
  source                  = "./modules/iam"
  name_prefix             = var.name_prefix
  database_url_secret_arn = module.secrets.database_url_secret_arn
  anthropic_api_key_arn   = module.secrets.anthropic_api_key_arn
  archive_bucket_arn      = module.storage.bucket_arn
  demo_sessions_table_arn = module.dynamodb.table_arn
  model_provider          = var.model_provider
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "disabled" # extra CloudWatch cost the student budget doesn't need
  }
  tags = { Name = "${var.name_prefix}-cluster" }
}

# -- the four always-on services --------------------------------------------

module "mediator" {
  source               = "./modules/ecs_service"
  name_prefix          = var.name_prefix
  service_name         = "mediator"
  cluster_id           = aws_ecs_cluster.this.id
  image                = var.mediator_image
  container_port       = 8000
  use_fargate_spot     = var.use_fargate_spot
  task_role_arn        = module.iam.mediator_task_role_arn
  execution_role_arn   = module.iam.ecs_execution_role_arn
  subnet_ids           = module.network.public_subnet_ids
  assign_public_ip     = true
  service_registry_arn = module.service_discovery.mediator_registry_arn
  environment = {
    RECORDER_URL                   = module.service_discovery.recorder_url
    MODEL_PROVIDER                 = var.model_provider
    AWS_REGION                     = var.aws_region
    BLACKBOX_KILL_SWITCH_SSM_PARAM = module.alerting.kill_switch_param_name
  }
  secrets = merge(
    { DATABASE_URL = module.secrets.database_url_secret_arn },
    var.model_provider == "anthropic" ? { ANTHROPIC_API_KEY = module.secrets.anthropic_api_key_arn } : {},
  )
}

module "recorder" {
  source               = "./modules/ecs_service"
  name_prefix          = var.name_prefix
  service_name         = "recorder"
  cluster_id           = aws_ecs_cluster.this.id
  image                = var.recorder_image
  container_port       = 8010
  use_fargate_spot     = var.use_fargate_spot
  task_role_arn        = module.iam.recorder_task_role_arn
  execution_role_arn   = module.iam.ecs_execution_role_arn
  subnet_ids           = module.network.public_subnet_ids
  assign_public_ip     = true
  service_registry_arn = module.service_discovery.recorder_registry_arn
  environment = {
    ARCHIVE_S3_BUCKET = module.storage.bucket_name
  }
  secrets = {
    DATABASE_URL = module.secrets.database_url_secret_arn
  }
}

module "demo" {
  source               = "./modules/ecs_service"
  name_prefix          = var.name_prefix
  service_name         = "demo"
  cluster_id           = aws_ecs_cluster.this.id
  image                = var.demo_image
  container_port       = 8020
  use_fargate_spot     = var.use_fargate_spot
  task_role_arn        = module.iam.demo_task_role_arn
  execution_role_arn   = module.iam.ecs_execution_role_arn
  subnet_ids           = module.network.public_subnet_ids
  assign_public_ip     = true
  service_registry_arn = module.service_discovery.demo_registry_arn
  environment = {
    MEDIATOR_URL                   = module.service_discovery.mediator_url
    RECORDER_URL                   = module.service_discovery.recorder_url
    BLACKBOX_KILL_SWITCH_SSM_PARAM = module.alerting.kill_switch_param_name
  }
}

module "investigator" {
  source                                = "./modules/ecs_service"
  name_prefix                           = var.name_prefix
  service_name                          = "investigator"
  cluster_id                            = aws_ecs_cluster.this.id
  image                                 = var.investigator_image
  container_port                        = 3000
  use_fargate_spot                      = var.use_fargate_spot
  task_role_arn                         = module.iam.investigator_task_role_arn
  execution_role_arn                    = module.iam.ecs_execution_role_arn
  subnet_ids                            = module.network.public_subnet_ids
  assign_public_ip                      = true
  target_group_arn                      = module.alb.investigator_target_group_arn
  additional_ingress_security_group_ids = [module.alb.alb_security_group_id]
  environment = {
    MEDIATOR_URL = module.service_discovery.mediator_url
    RECORDER_URL = module.service_discovery.recorder_url
    DEMO_URL     = module.service_discovery.demo_url
  }
}

# -- ephemeral agent task definition — launched on demand by the demo
#    service via ecs:RunTask, never as a persistent aws_ecs_service. Runs
#    in the no-NAT "agent" subnets from modules/network.

resource "aws_security_group" "agent_task" {
  name        = "${var.name_prefix}-agent-task-sg"
  description = "Agent tasks: no inbound, egress restricted to the mediator only (I3's network posture)"
  vpc_id      = module.network.vpc_id

  egress {
    description     = "Mediator only — no other destination, and the agent subnet route table has no internet route at all"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [module.mediator.security_group_id]
  }
  tags = { Name = "${var.name_prefix}-agent-task-sg" }
}

resource "aws_cloudwatch_log_group" "agent_task" {
  name              = "/ecs/${var.name_prefix}-agent-task"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "agent" {
  family                   = "${var.name_prefix}-agent-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = module.iam.ecs_execution_role_arn
  # Deliberately NO task_role_arn — an agent task holding an IAM role at
  # all would be a credential the agent has, which I3 forbids. It talks to
  # the mediator with a session token only.

  container_definitions = jsonencode([{
    name      = "agent"
    image     = var.demo_image # same backend.Dockerfile image; entrypoint overridden per RunTask invocation
    essential = true
    environment = [
      { name = "MEDIATOR_BASE_URL", value = module.service_discovery.mediator_url },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.agent_task.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "agent"
      }
    }
  }])

  tags = { Name = "${var.name_prefix}-agent-task" }
}
