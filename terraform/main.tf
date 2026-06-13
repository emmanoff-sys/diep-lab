# DIEP infrastructure (Phase 10A) — Terraform skeleton.
# Provisions the cluster + the platform namespace, operators, and the secret backend.
# Cloud-agnostic shape; swap the cluster module for EKS/GKE/AKS as needed.

terraform {
  required_version = ">= 1.5"
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.30" }
    helm       = { source = "hashicorp/helm", version = "~> 2.13" }
  }
  # Remote state (never local in prod).
  backend "s3" {
    bucket = "diep-tfstate"
    key    = "diep/terraform.tfstate"
    region = "eu-west-1"
  }
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "cluster_name" {
  type    = string
  default = "diep"
}

# --- cluster (swap for your cloud) ---------------------------------------
# module "cluster" {
#   source       = "terraform-aws-modules/eks/aws"   # or GKE/AKS equivalent
#   cluster_name = var.cluster_name
#   ...          # node groups across >=3 AZs, autoscaling, OIDC for IRSA
# }

# --- platform namespace ---------------------------------------------------
resource "kubernetes_namespace" "diep" {
  metadata { name = "diep" }
}

# --- operators (datastore HA, per k8s/) -----------------------------------
# Installed via Helm: CloudNativePG, Strimzi (Kafka), Redis (Sentinel),
# cert-manager, ingress-nginx, external-secrets (Vault). Example:
# resource "helm_release" "cnpg" {
#   name = "cnpg"  repository = "https://cloudnative-pg.github.io/charts"
#   chart = "cloudnative-pg"  namespace = "cnpg-system"  create_namespace = true
# }

# --- secrets backend ------------------------------------------------------
# Vault (HA) provides KV (app secrets) + PKI (the MQTT/device CA). The
# External Secrets Operator syncs Vault -> the diep-secrets k8s Secret.
# See DIEP_PHASE9J reports for the secret/PKI design.

output "namespace" { value = kubernetes_namespace.diep.metadata[0].name }
