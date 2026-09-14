# One repository per service. Kept as its own module (rather than inline
# in root main.tf) so the images can be built and pushed before the rest
# of the stack references them — `terraform apply -target=module.ecr`
# first, then build/push, then a full apply.

variable "name_prefix" { type = string }

locals {
  services = ["mediator", "recorder", "demo", "investigator"]
}

resource "aws_ecr_repository" "this" {
  for_each             = toset(local.services)
  name                 = "${var.name_prefix}-${each.value}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
  tags = { Name = "${var.name_prefix}-${each.value}" }
}

# Keeps the account from quietly accumulating untagged layers (and their
# storage cost) across repeated `make ecr-push` runs during the
# deploy-verify-teardown cycle.
resource "aws_ecr_lifecycle_policy" "expire_untagged" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images after 3 days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}

output "repository_urls" {
  value = { for k, v in aws_ecr_repository.this : k => v.repository_url }
}
