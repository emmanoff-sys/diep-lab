# DAEP / RE-OS — Terraform VM module variables (WP-003-08)
# Authority: LLD v2.0 §17.3 (direct, literal source)

variable "service_name" {
  description = "RE-OS service name — used for resource naming/tagging."
  type        = string
}

variable "instance_count" {
  description = "Number of VM instances (default 2, for HA per LLD §17.2's 2-backend Nginx upstream examples)."
  type        = number
  default     = 2
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.medium"
}

variable "disk_size_gb" {
  description = "Root volume size in GB."
  type        = number
  default     = 30
}

variable "environment" {
  description = "Deployment environment — Roadmap v1.0 §11.2 canonical set."
  type        = string
  validation {
    condition     = contains(["local", "shared_dev", "ci", "staging", "production", "integration", "qa", "uat", "dr"], var.environment)
    error_message = "environment must be one of the Roadmap v1.0 §11.2 environment names."
  }
}

variable "subnet_ids" {
  description = "Pre-existing subnet IDs (networking module is a separate, documented dependency — WP-003-08 §9)."
  type        = list(string)
}

variable "security_group_id" {
  description = "Pre-existing security group ID (aws_security_group.service.id, per LLD §17.3)."
  type        = string
}

variable "vault_addr" {
  description = "Vault server URL, rendered into cloud-init (WP-003-13)."
  type        = string
}

variable "kms_key_id" {
  description = "KMS key ID for root volume encryption."
  type        = string
}
