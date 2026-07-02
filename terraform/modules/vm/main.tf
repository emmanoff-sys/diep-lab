# DAEP / RE-OS — Terraform VM module (WP-003-08)
# Authority: LLD v2.0 §17.3 (direct, literal source)
#
# NOT EXECUTED: no `terraform apply`/`destroy` has been run against any AWS
# account by this implementation — see TERRAFORM_STANDARDS.md §7.

data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "reos_service" {
  count = var.instance_count

  ami           = data.aws_ami.ubuntu_2204.id
  instance_type = var.instance_type
  subnet_id     = element(var.subnet_ids, count.index % length(var.subnet_ids))

  vpc_security_group_ids = [var.security_group_id]

  root_block_device {
    volume_type = "gp3"
    volume_size = var.disk_size_gb
    encrypted   = true
    kms_key_id  = var.kms_key_id
  }

  # IMDSv2-only — hardening against SSRF-based credential theft (WP-003-08 §15).
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = templatefile("${path.module}/../../../infra/vm-base/cloud-init.yml.tftpl", {
    service_name = var.service_name
    environment  = var.environment
    vault_addr   = var.vault_addr
  })

  tags = {
    Name        = "reos-${var.service_name}-${var.environment}-${count.index}"
    Service     = var.service_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
