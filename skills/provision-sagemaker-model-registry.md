---
name: provision-sagemaker-model-registry
title: Provision SageMaker Model Registry
type: skill
topics:
  - terraform
  - aws
  - sagemaker
  - mlops
  - infrastructure-as-code
summary: >
  Provision an AWS SageMaker Model Package Group using Terraform for versioned
  model tracking, with least-privilege IAM for registering and approving models,
  optional KMS encryption, and configurable tagging for governed model lifecycle.
references:
  - skills/scaffold-terraform-aws-repo.md
  - articles/ai-ml/sagemaker-ml-platform.md
last-updated: 2026-06-25
---

# Provision SageMaker Model Registry

Create a SageMaker Model Package Group for versioned model tracking with IAM
access patterns, optional encryption, and tagging. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)
- KMS key created if encryption is required (pass ARN via `kms_key_id`)
- Baseline SageMaker execution role if models will be registered from training
  pipelines or notebooks

---

## Steps

### Step 1: Define variables

```hcl
variable "model_package_group_name" {
  description = "Name of the SageMaker Model Package Group"
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$", var.model_package_group_name))
    error_message = "model_package_group_name must be 1-63 alphanumeric characters or hyphens, starting and ending with alphanumeric."
  }
}

variable "model_package_group_description" {
  description = "Description of the Model Package Group"
  type        = string
  default     = ""
}

variable "approval_status" {
  description = "Default ModelApprovalStatus for new model packages (PendingManualApproval, Approved, Rejected)"
  type        = string
  default     = "PendingManualApproval"

  validation {
    condition     = contains(["PendingManualApproval", "Approved", "Rejected"], var.approval_status)
    error_message = "approval_status must be PendingManualApproval, Approved, or Rejected."
  }
}

variable "kms_key_id" {
  description = "ARN of the KMS key for encrypting model artifacts (empty string to disable)"
  type        = string
  default     = ""
}

variable "allowed_principal_arns" {
  description = "List of IAM principal ARNs allowed to register and describe model packages"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region for the Model Registry resources"
  type        = string
}
```

### Step 2: Add data sources

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
```

### Step 3: Create the Model Package Group

```hcl
resource "aws_sagemaker_model_package_group" "this" {
  model_package_group_name        = var.model_package_group_name
  model_package_group_description = var.model_package_group_description

  tags = merge(var.tags, {
    Environment    = var.environment
    ApprovalStatus = var.approval_status
  })
}
```

### Step 4: Create Model Package Group resource policy (conditional)

```hcl
resource "aws_sagemaker_model_package_group_policy" "this" {
  count                    = length(var.allowed_principal_arns) > 0 ? 1 : 0
  model_package_group_name = aws_sagemaker_model_package_group.this.model_package_group_name

  resource_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowDescribeModelPackageGroup"
        Effect = "Allow"
        Principal = {
          AWS = var.allowed_principal_arns
        }
        Action = [
          "sagemaker:DescribeModelPackageGroup",
        ]
        Resource = aws_sagemaker_model_package_group.this.arn
      },
      {
        Sid    = "AllowModelPackageOperations"
        Effect = "Allow"
        Principal = {
          AWS = var.allowed_principal_arns
        }
        Action = [
          "sagemaker:CreateModelPackage",
          "sagemaker:DescribeModelPackage",
          "sagemaker:ListModelPackages",
        ]
        Resource = "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model-package/${var.model_package_group_name}/*"
      },
    ]
  })
}
```

### Step 5: Create IAM policy for model registration

```hcl
resource "aws_iam_policy" "model_register" {
  name        = "${var.model_package_group_name}-register"
  description = "Allows registering model packages in ${var.model_package_group_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DescribeModelPackageGroup"
        Effect = "Allow"
        Action = [
          "sagemaker:DescribeModelPackageGroup",
        ]
        Resource = aws_sagemaker_model_package_group.this.arn
      },
      {
        Sid    = "RegisterModelPackage"
        Effect = "Allow"
        Action = [
          "sagemaker:CreateModelPackage",
          "sagemaker:DescribeModelPackage",
          "sagemaker:ListModelPackages",
        ]
        Resource = "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model-package/${var.model_package_group_name}/*"
      },
    ]
  })

  tags = var.tags
}
```

### Step 6: Create IAM policy for model approval

```hcl
resource "aws_iam_policy" "model_approve" {
  name        = "${var.model_package_group_name}-approve"
  description = "Allows approving or rejecting model packages in ${var.model_package_group_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ApproveModelPackage"
        Effect = "Allow"
        Action = [
          "sagemaker:UpdateModelPackage",
        ]
        Resource = "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model-package/${var.model_package_group_name}/*"
      },
      {
        Sid    = "DescribeForApproval"
        Effect = "Allow"
        Action = [
          "sagemaker:DescribeModelPackage",
          "sagemaker:ListModelPackages",
        ]
        Resource = "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model-package/${var.model_package_group_name}/*"
      },
    ]
  })

  tags = var.tags
}
```

### Step 7: Create KMS grant policy (conditional)

```hcl
resource "aws_iam_policy" "model_kms" {
  count       = var.kms_key_id != "" ? 1 : 0
  name        = "${var.model_package_group_name}-kms"
  description = "Allows encrypt/decrypt for model artifacts in ${var.model_package_group_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSModelArtifacts"
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
        ]
        Resource = var.kms_key_id
      },
    ]
  })

  tags = var.tags
}
```

### Step 8: Define outputs

```hcl
output "model_package_group_arn" {
  description = "ARN of the SageMaker Model Package Group"
  value       = aws_sagemaker_model_package_group.this.arn
}

output "model_package_group_name" {
  description = "Name of the SageMaker Model Package Group"
  value       = aws_sagemaker_model_package_group.this.model_package_group_name
}

output "register_policy_arn" {
  description = "ARN of the IAM policy for registering model packages"
  value       = aws_iam_policy.model_register.arn
}

output "approve_policy_arn" {
  description = "ARN of the IAM policy for approving model packages"
  value       = aws_iam_policy.model_approve.arn
}

output "kms_policy_arn" {
  description = "ARN of the IAM policy for KMS access (empty if encryption disabled)"
  value       = var.kms_key_id != "" ? aws_iam_policy.model_kms[0].arn : ""
}
```

### Step 9: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 10: Commit and PR

```bash
git add .
git commit -m "Add SageMaker Model Registry (Model Package Group)"
gh pr create --title "Provision SageMaker Model Registry" --body "Adds Model Package Group, resource policy, registration and approval IAM policies, optional KMS encryption, and tagging"
```

---

## Examples

### Basic model registry without encryption

```hcl
module "model_registry" {
  source = "./modules/sagemaker-model-registry"

  model_package_group_name        = "fraud-detection"
  model_package_group_description = "Fraud detection model versions"
  approval_status                 = "PendingManualApproval"
  environment                     = "dev"
  region                          = "us-east-1"
  tags                            = { Team = "ml-platform" }
}
```

### Encrypted registry with cross-account access

```hcl
module "model_registry" {
  source = "./modules/sagemaker-model-registry"

  model_package_group_name        = "recommendation-engine"
  model_package_group_description = "Recommendation model versions with KMS encryption"
  approval_status                 = "PendingManualApproval"
  kms_key_id                      = "arn:aws:kms:us-east-1:111111111111:key/abcd-1234-efgh-5678"
  environment                     = "prod"
  region                          = "us-east-1"

  allowed_principal_arns = [
    "arn:aws:iam::222222222222:role/MLEngineerRole",
    "arn:aws:iam::333333333333:role/DataScienceRole",
  ]

  tags = {
    Team       = "ml-platform"
    CostCenter = "ml-ops"
  }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Use `aws_sagemaker_model_package_group` resource | Native Terraform resource for model versioning; not ad hoc placeholders |
| Default approval status `PendingManualApproval` | Enforces human review before models reach production |
| Resource policy scoped to exact Model Package Group ARN | No wildcard resources; principals restricted to `allowed_principal_arns` |
| Separate IAM policies for registration and approval | Least-privilege separation of duties between ML engineers and approvers |
| KMS policy conditional on `kms_key_id` | Encryption only when required by policy; no unnecessary KMS grants |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with `var.tags` plus environment | Consistent cost tracking, governance, and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |
| Model Package Group name validated (1-63 chars) | Prevents API errors from invalid naming at plan time |

---

## Outputs

- SageMaker Model Package Group for versioned model tracking
- Resource policy granting scoped cross-account access (conditional)
- IAM policy for model registration (create, describe, list model packages)
- IAM policy for model approval (update model package approval status)
- Optional KMS policy for encrypted model artifact access
- Model Package Group ARN, name, and policy ARNs exported
