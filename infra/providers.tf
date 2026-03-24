terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "heatwave-tf-state-388691194728"
    key            = "heatwave/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "heatwave-tf-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project     = "heatwave"
      environment = var.environment
      managed_by  = "terraform"
    }
  }
}
