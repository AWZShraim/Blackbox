# One reusable Fargate service definition, used for mediator, recorder,
# demo, and investigator (Section 9: "Mediator: ECS Fargate behind an
# ALB", "Recorder: ECS Fargate, separate service (I1)" — a genuinely
# separate aws_ecs_service per component, not four containers in one task
# definition, which is what actually makes I1 true at the infrastructure
# level and not just in application code).

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name_prefix}-${var.service_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name_prefix}-${var.service_name}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = var.service_name
    image     = var.image
    essential = true
    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]
    environment = [for k, v in var.environment : { name = k, value = v }]
    secrets     = [for k, arn in var.secrets : { name = k, valueFrom = arn }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = var.service_name
      }
    }
  }])

  tags = { Name = "${var.name_prefix}-${var.service_name}" }
}

data "aws_region" "current" {}

resource "aws_ecs_service" "this" {
  name            = "${var.name_prefix}-${var.service_name}"
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count

  dynamic "capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = 1
    }
  }
  # On-demand Fargate when not using Spot — mutually exclusive with the
  # capacity_provider_strategy block above.
  launch_type = var.use_fargate_spot ? null : "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = var.assign_public_ip
  }

  dynamic "service_registries" {
    for_each = var.service_registry_arn != null ? [1] : []
    content {
      registry_arn = var.service_registry_arn
    }
  }

  dynamic "load_balancer" {
    for_each = var.target_group_arn != null ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.service_name
      container_port   = var.container_port
    }
  }

  tags = { Name = "${var.name_prefix}-${var.service_name}" }
}

resource "aws_security_group" "service" {
  name        = "${var.name_prefix}-${var.service_name}-sg"
  description = "Traffic for the ${var.service_name} service"
  vpc_id      = data.aws_vpc.selected.id

  ingress {
    description = "Container port from within the VPC"
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }
  dynamic "ingress" {
    for_each = var.additional_ingress_security_group_ids
    content {
      description     = "Container port from an explicitly allowed security group"
      from_port       = var.container_port
      to_port         = var.container_port
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name_prefix}-${var.service_name}-sg" }
}

data "aws_vpc" "selected" {
  # Derived from the first subnet passed in, so callers don't have to pass
  # vpc_id separately just for this one security group.
  id = data.aws_subnet.first.vpc_id
}

data "aws_subnet" "first" {
  id = var.subnet_ids[0]
}

output "security_group_id" { value = aws_security_group.service.id }
output "task_definition_arn" { value = aws_ecs_task_definition.this.arn }
output "service_name" { value = aws_ecs_service.this.name }
