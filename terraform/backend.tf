# DAEP / RE-OS — Terraform remote state backend (WP-003-08)
#
# FLAGGED (WP-003-08 §15/§35, not silently invented): the LLD v2.0 §17.3
# excerpt does not show a backend block explicitly. S3 + DynamoDB lock table
# is standard Terraform practice and is implied by the LLD's multi-
# environment, multi-engineer usage pattern, but this specific choice (vs.
# Terraform Cloud or another remote-state option) has NOT been confirmed by
# the Project Owner. Treat this as a proposed default pending confirmation,
# not settled architecture — see TERRAFORM_STANDARDS.md §5.

terraform {
  backend "s3" {
    bucket         = "reos-terraform-state"          # placeholder — confirm real bucket name
    key            = "vm/terraform.tfstate"           # overridden per-environment via -backend-config
    region         = "eu-west-1"                       # placeholder — confirm real region
    dynamodb_table = "reos-terraform-locks"
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  required_version = ">= 1.7.0"
}
