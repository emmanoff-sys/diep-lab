# DAEP / RE-OS — Terraform VM module outputs (WP-003-08)

output "instance_ids" {
  description = "IDs of the provisioned EC2 instances."
  value       = aws_instance.reos_service[*].id
}

output "private_ips" {
  description = "Private IPv4 addresses of the provisioned instances."
  value       = aws_instance.reos_service[*].private_ip
}

output "instance_count" {
  description = "Number of instances actually provisioned."
  value       = length(aws_instance.reos_service)
}
