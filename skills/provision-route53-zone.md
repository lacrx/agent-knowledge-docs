---
name: provision-route53-zone
title: Provision Route 53 Hosted Zone
type: skill
topics:
  - terraform
  - aws
  - route53
  - dns
  - infrastructure-as-code
summary: >
  Provision an AWS Route 53 hosted zone using Terraform with support for public
  or private DNS zones, optional VPC association for private zones, standard
  tagging, and reusable outputs for downstream DNS record configuration.
references:
  - skills/scaffold-terraform-aws-repo.md
  - articles/aws/aws-web-app-networking.md
last-updated: 2026-06-25
---

# Provision Route 53 Hosted Zone

Create a Route 53 hosted zone for public or private DNS resolution with
standard tagging and exported outputs. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- For private zones: target VPC must already exist
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)
- Domain name registered or delegated (for public zones)

---

## Steps

### Step 1: Define variables

```hcl
variable "zone_name" {
  description = "Fully qualified domain name for the hosted zone (e.g. example.com)"
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$", var.zone_name))
    error_message = "zone_name must be a valid domain name."
  }
}

variable "comment" {
  description = "Comment for the hosted zone"
  type        = string
  default     = ""
}

variable "private_zone" {
  description = "Whether this is a private hosted zone associated with a VPC"
  type        = bool
  default     = false
}

variable "vpc_id" {
  description = "VPC ID to associate with the private hosted zone (required when private_zone = true)"
  type        = string
  default     = ""
}

variable "vpc_region" {
  description = "Region of the VPC to associate with the private hosted zone (defaults to provider region)"
  type        = string
  default     = ""
}

variable "force_destroy" {
  description = "Whether to destroy the zone even if it contains records (use with caution)"
  type        = bool
  default     = false
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region for the provider"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
```

### Step 2: Add validation locals

```hcl
locals {
  # Merge standard tags with user-supplied tags
  merged_tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags,
  )
}
```

### Step 3: Add precondition checks

```hcl
resource "terraform_data" "private_zone_validation" {
  count = var.private_zone ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.vpc_id != ""
      error_message = "vpc_id is required when private_zone is true."
    }
  }
}
```

### Step 4: Create the public hosted zone (conditional)

```hcl
resource "aws_route53_zone" "public" {
  count = var.private_zone ? 0 : 1

  name          = var.zone_name
  comment       = var.comment != "" ? var.comment : "Public zone for ${var.zone_name}"
  force_destroy = var.force_destroy

  tags = local.merged_tags
}
```

### Step 5: Create the private hosted zone (conditional)

```hcl
resource "aws_route53_zone" "private" {
  count = var.private_zone ? 1 : 0

  name          = var.zone_name
  comment       = var.comment != "" ? var.comment : "Private zone for ${var.zone_name}"
  force_destroy = var.force_destroy

  vpc {
    vpc_id     = var.vpc_id
    vpc_region = var.vpc_region != "" ? var.vpc_region : var.region
  }

  tags = local.merged_tags
}
```

### Step 6: Define outputs

```hcl
output "zone_id" {
  description = "ID of the Route 53 hosted zone"
  value       = var.private_zone ? aws_route53_zone.private[0].zone_id : aws_route53_zone.public[0].zone_id
}

output "zone_arn" {
  description = "ARN of the Route 53 hosted zone"
  value       = var.private_zone ? aws_route53_zone.private[0].arn : aws_route53_zone.public[0].arn
}

output "name_servers" {
  description = "List of name servers for the hosted zone (empty for private zones)"
  value       = var.private_zone ? [] : aws_route53_zone.public[0].name_servers
}
```

### Step 7: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 8: Commit and PR

```bash
git add .
git commit -m "Add Route 53 hosted zone"
gh pr create --title "Provision Route 53 hosted zone" --body "Adds Route 53 hosted zone with public/private support, VPC association, tagging, and reusable outputs"
```

---

## Examples

### Public zone

```hcl
module "public_zone" {
  source = "./modules/route53-zone"

  zone_name     = "example.com"
  comment       = "Production public zone"
  private_zone  = false
  force_destroy = false
  environment   = "prod"
  region        = "us-east-1"
  tags          = { Team = "platform" }
}
```

### Private zone with VPC association

```hcl
module "private_zone" {
  source = "./modules/route53-zone"

  zone_name     = "internal.example.com"
  comment       = "Internal service discovery zone"
  private_zone  = true
  vpc_id        = aws_vpc.main.id
  vpc_region    = "us-east-1"
  force_destroy = false
  environment   = "prod"
  region        = "us-east-1"
  tags          = { Team = "platform" }
}
```

### Downstream record using zone outputs

```hcl
resource "aws_route53_record" "api" {
  zone_id = module.public_zone.zone_id
  name    = "api.example.com"
  type    = "A"

  alias {
    name                   = aws_lb.api.dns_name
    zone_id                = aws_lb.api.zone_id
    evaluate_target_health = true
  }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Separate resources for public and private zones | Avoids invalid mixed configuration; `vpc` block is incompatible with public zones |
| Require `vpc_id` when `private_zone = true` | Private zones must have at least one VPC association at creation time |
| Ignore `vpc_id` and `vpc_region` when `private_zone = false` | Prevents accidental creation of a private zone when a public zone is intended |
| `force_destroy` defaults to `false` | Protects against accidental deletion of zones containing records |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with merged tags | Consistent cost tracking and resource identification; environment and ManagedBy always present |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- Route 53 hosted zone (public or private) with configurable domain name and comment
- VPC association for private zones with region-aware configuration
- Precondition validation ensuring VPC inputs are provided for private zones
- Standard merged tags including environment and ManagedBy on all resources
- Zone ID, zone ARN, and name servers exported for downstream DNS record creation
- Force-destroy flag for controlled teardown of zones with existing records
