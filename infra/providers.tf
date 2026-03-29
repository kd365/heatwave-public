terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
  }

  # Using local state for personal deployment
  # To use S3 remote state, bootstrap with infra/bootstrap/bootstrap.sh
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region  = var.aws_region
  profile = "cyber-risk"

  default_tags {
    tags = {
      project     = "heatwave"
      environment = var.environment
      managed_by  = "terraform"
    }
  }
}
