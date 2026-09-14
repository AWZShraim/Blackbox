# Internal service discovery for mediator/recorder/demo. Only the
# Investigator sits behind the public ALB (modules/alb) — everything else
# (the mediator, the recorder, the demo orchestrator, and agent tasks
# reaching the mediator) talks over this private DNS namespace instead,
# entirely inside the VPC. That is a stronger, cheaper version of the same
# idea as the agent's no-NAT subnet: the fewer things exposed to the public
# internet, the fewer things that can be reached from outside it.

variable "name_prefix" { type = string }
variable "vpc_id" { type = string }

resource "aws_service_discovery_private_dns_namespace" "this" {
  name = "${var.name_prefix}.local"
  vpc  = var.vpc_id
}

resource "aws_service_discovery_service" "mediator" {
  name = "mediator"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "recorder" {
  name = "recorder"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "demo" {
  name = "demo"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

output "namespace_id" { value = aws_service_discovery_private_dns_namespace.this.id }
output "namespace_name" { value = aws_service_discovery_private_dns_namespace.this.name }
output "mediator_registry_arn" { value = aws_service_discovery_service.mediator.arn }
output "recorder_registry_arn" { value = aws_service_discovery_service.recorder.arn }
output "demo_registry_arn" { value = aws_service_discovery_service.demo.arn }
output "mediator_url" { value = "http://mediator.${aws_service_discovery_private_dns_namespace.this.name}:8000" }
output "recorder_url" { value = "http://recorder.${aws_service_discovery_private_dns_namespace.this.name}:8010" }
output "demo_url" { value = "http://demo.${aws_service_discovery_private_dns_namespace.this.name}:8020" }
