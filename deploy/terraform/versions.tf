terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    # Resource tagging for cost attribution (Section 9 / user requirement):
    # every resource this stack creates carries these, so a Cost Explorer
    # filter on Project=blackbox gives an exact bill for the stack alone.
    tags = {
      Project   = "blackbox"
      Profile   = var.profile_name
      ManagedBy = "terraform"
      Ephemeral = "true"
    }
  }
}
