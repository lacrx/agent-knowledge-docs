---
name: provision-ecr-repository
title: Provision ECR Repository
type: skill
topics:
  - terraform
  - aws
  - ecr
  - infrastructure-as-code
  - containerization
summary: >
  Provision an AWS ECR private repository using Terraform with immutable tags,
  scan-on-push, lifecycle policies, least-privilege pull access, and optional
  multi-region replication.
references:
  - skills/scaffold-terraform-aws-repo.md
  - skills/create-python-dockerfile.md
  - skills/create-nextjs-dockerfile.md
  - articles/aws/aws-web-app-networking.md
last-updated: 2026-06-15
---

# Provision ECR Repository

Create a private ECR repository with image scanning, lifecycle management,
and scoped pull access. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- IAM role for the workload (ECS task role, Lambda role, etc.) that needs to pull images

---

## Steps

### Step 1: Define variables

```hcl
variable "repository_name" {
  description = "Name of the ECR repository"
  type        = string
}

variable "image_tag_mutability" {
  description = "Tag mutability setting (MUTABLE or IMMUTABLE)"
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "max_image_count" {
  description = "Maximum number of tagged images to retain"
  type        = number
  default     = 30
}

variable "untagged_expiry_days" {
  description = "Days before untagged images are expired"
  type        = number
  default     = 14
}

variable "pull_access_arns" {
  description = "List of IAM ARNs that can pull images from this repository"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
```

### Step 2: Add data sources

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
```

### Step 3: Create ECR repository

```hcl
resource "aws_ecr_repository" "this" {
  name                 = var.repository_name
  image_tag_mutability = var.image_tag_mutability

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}
```

### Step 4: Create lifecycle policy

```hcl
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.untagged_expiry_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_expiry_days
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only last ${var.max_image_count} tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha-", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = var.max_image_count
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}
```

### Step 5: Create repository policy for pull access

```hcl
resource "aws_ecr_repository_policy" "this" {
  count      = length(var.pull_access_arns) > 0 ? 1 : 0
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPull"
        Effect = "Allow"
        Principal = {
          AWS = var.pull_access_arns
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
        ]
      },
    ]
  })
}
```

### Step 6: (Optional) Create replication configuration for multi-region

```hcl
variable "replica_regions" {
  description = "List of regions to replicate images to (leave empty to skip)"
  type        = list(string)
  default     = []
}

resource "aws_ecr_replication_configuration" "this" {
  count = length(var.replica_regions) > 0 ? 1 : 0

  replication_configuration {
    rule {
      dynamic "destination" {
        for_each = var.replica_regions
        content {
          region      = destination.value
          registry_id = data.aws_caller_identity.current.account_id
        }
      }

      repository_filter {
        filter      = var.repository_name
        filter_type = "PREFIX_MATCH"
      }
    }
  }
}
```

### Step 7: Define outputs

```hcl
output "repository_url" {
  description = "Full URL of the ECR repository (use for docker push/pull)"
  value       = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.this.arn
}

output "registry_id" {
  description = "Registry ID (AWS account ID)"
  value       = aws_ecr_repository.this.registry_id
}
```

### Step 8: Docker login and push

```bash
# Authenticate Docker to ECR
aws ecr get-login-password --region $(terraform output -raw aws_region) \
  | docker login --username AWS --password-stdin \
    $(terraform output -raw repository_url | cut -d'/' -f1)

# Tag and push
docker tag my-app:latest $(terraform output -raw repository_url):v1.0.0
docker push $(terraform output -raw repository_url):v1.0.0
```

### Step 9: Format, commit, and PR

```bash
terraform fmt -recursive
git add .
git commit -m "Add ECR repository for ${repository_name}"
gh pr create --title "Provision ECR repository" --body "Adds ECR repo with lifecycle policy, scan-on-push, and pull access"
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Image tag mutability defaults to IMMUTABLE | Prevents tag overwrites in production |
| Image scanning on push enabled | Catches CVEs at push time |
| Lifecycle policy is mandatory | Prevents unbounded storage cost growth |
| No `ecr:*` wildcards in repository policy | Least privilege — only pull actions granted |
| No hard-coded account IDs | Use `data.aws_caller_identity` for account reference |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |

---

## Outputs

- ECR private repository with immutable tags and scan-on-push
- Lifecycle policy expiring untagged images and capping tagged image count
- Repository policy granting least-privilege pull access to specified IAM roles
- Optional multi-region replication configuration
- Docker login and push commands using repository URL output
