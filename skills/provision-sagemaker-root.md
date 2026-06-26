---
name: provision-sagemaker-root
title: Provision SageMaker Root
type: skill
topics:
  - terraform
  - aws
  - sagemaker
  - machine-learning
  - infrastructure-as-code
summary: >
  Provision baseline SageMaker platform resources via Terraform including a core
  IAM execution role, S3 artifact bucket, shared networking configuration, and
  KMS encryption support that downstream SageMaker skills depend on.
references:
  - skills/provision-sagemaker-training.md
  - skills/provision-sagemaker-model-registry.md
  - articles/ai-ml/sagemaker-ml-platform.md
last-updated: 2026-06-25
---

# Provision SageMaker Root

Create the foundational SageMaker platform resources that all downstream
SageMaker modules depend on: a shared IAM execution role, an S3 artifact bucket,
and optional VPC security and KMS encryption configuration. Follow steps in
order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)
- (Optional) Existing VPC with private subnets if VPC-mode SageMaker is needed
- (Optional) KMS key ARN if at-rest encryption is required for the artifact bucket
- No secrets committed to `.tf` or `.tfvars` files

---

## Steps

### Step 1: Define variables

```hcl
variable "project_name" {
  description = "Project name used as a prefix for all resource names"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 2-32 lowercase alphanumeric characters or hyphens."
  }
}

variable "sagemaker_execution_role_name" {
  description = "Name for the shared IAM role that SageMaker services assume"
  type        = string
}

variable "artifact_bucket_name" {
  description = "Name for the S3 bucket storing SageMaker artifacts (models, data, outputs)"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the KMS key for encrypting the artifact bucket and SageMaker volumes (empty to use AES256)"
  type        = string
  default     = ""
}

variable "vpc_id" {
  description = "VPC ID for SageMaker workloads (empty to skip VPC security group creation)"
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for SageMaker VPC mode (empty to skip)"
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "List of existing security group IDs to use for SageMaker VPC mode (empty to create a new one)"
  type        = list(string)
  default     = []
}

variable "enable_network_isolation" {
  description = "Whether SageMaker containers should run in network isolation mode"
  type        = bool
  default     = false
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
  description = "AWS region for all resources"
  type        = string
}
```

### Step 2: Add data sources and locals

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id     = data.aws_caller_identity.current.account_id
  region         = data.aws_region.current.name
  use_kms        = var.kms_key_arn != ""
  use_vpc        = var.vpc_id != ""
  create_sg      = local.use_vpc && length(var.security_group_ids) == 0
  sg_ids         = local.create_sg ? [aws_security_group.sagemaker[0].id] : var.security_group_ids
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
```

### Step 3: Create the shared IAM execution role

```hcl
resource "aws_iam_role" "sagemaker_execution" {
  name = var.sagemaker_execution_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SageMakerAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = local.account_id
          }
        }
      },
    ]
  })

  tags = local.common_tags
}
```

### Step 4: Create the S3 artifact bucket policy (scoped to artifact bucket)

```hcl
resource "aws_iam_role_policy" "sagemaker_s3" {
  name = "${var.sagemaker_execution_role_name}-s3-artifacts"
  role = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListArtifactBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = aws_s3_bucket.artifacts.arn
      },
      {
        Sid    = "ReadWriteArtifacts"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/*"
      },
    ]
  })
}
```

### Step 5: Create CloudWatch Logs policy

```hcl
resource "aws_iam_role_policy" "sagemaker_logs" {
  name = "${var.sagemaker_execution_role_name}-logs"
  role = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/sagemaker/*"
      },
    ]
  })
}
```

### Step 6: Create KMS policy (conditional)

```hcl
resource "aws_iam_role_policy" "sagemaker_kms" {
  count = local.use_kms ? 1 : 0
  name  = "${var.sagemaker_execution_role_name}-kms"
  role  = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSAccess"
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
        ]
        Resource = var.kms_key_arn
      },
    ]
  })
}
```

### Step 7: Create VPC networking policy (conditional)

```hcl
resource "aws_iam_role_policy" "sagemaker_vpc" {
  count = local.use_vpc ? 1 : 0
  name  = "${var.sagemaker_execution_role_name}-vpc"
  role  = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VPCNetworkInterface"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:CreateNetworkInterfacePermission",
          "ec2:DeleteNetworkInterface",
          "ec2:DeleteNetworkInterfacePermission",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeVpcs",
          "ec2:DescribeDhcpOptions",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
        ]
        Resource = "*"
      },
    ]
  })
}
```

### Step 8: Create the S3 artifact bucket

```hcl
resource "aws_s3_bucket" "artifacts" {
  bucket = var.artifact_bucket_name

  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = local.use_kms ? "aws:kms" : "AES256"
      kms_master_key_id = local.use_kms ? var.kms_key_arn : null
    }
    bucket_key_enabled = local.use_kms
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

### Step 9: Create SageMaker security group (conditional on vpc_id)

```hcl
resource "aws_security_group" "sagemaker" {
  count       = local.create_sg ? 1 : 0
  name        = "${var.project_name}-sagemaker-sg"
  description = "Security group for SageMaker workloads in ${var.project_name}"
  vpc_id      = var.vpc_id

  ingress {
    description = "Allow intra-SG traffic for distributed training"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    description = "Allow all outbound (set enable_network_isolation=true to restrict at SageMaker level)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-sagemaker-sg"
  })
}
```

### Step 10: Create a root configuration local for downstream modules

```hcl
locals {
  sagemaker_root_config = {
    project_name             = var.project_name
    execution_role_arn       = aws_iam_role.sagemaker_execution.arn
    artifact_bucket_name     = aws_s3_bucket.artifacts.bucket
    artifact_bucket_arn      = aws_s3_bucket.artifacts.arn
    kms_key_arn              = var.kms_key_arn
    vpc_id                   = var.vpc_id
    private_subnet_ids       = var.private_subnet_ids
    security_group_ids       = local.sg_ids
    enable_network_isolation = var.enable_network_isolation
  }
}
```

### Step 11: Define outputs

```hcl
output "execution_role_arn" {
  description = "ARN of the shared SageMaker execution IAM role"
  value       = aws_iam_role.sagemaker_execution.arn
}

output "artifact_bucket_arn" {
  description = "ARN of the S3 artifact bucket"
  value       = aws_s3_bucket.artifacts.arn
}

output "artifact_bucket_name" {
  description = "Name of the S3 artifact bucket"
  value       = aws_s3_bucket.artifacts.bucket
}

output "vpc_id" {
  description = "VPC ID used for SageMaker workloads (empty if VPC mode disabled)"
  value       = var.vpc_id
}

output "security_group_ids" {
  description = "Security group IDs for SageMaker VPC mode"
  value       = local.sg_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs for SageMaker VPC mode"
  value       = var.private_subnet_ids
}

output "sagemaker_root_config" {
  description = "Full root configuration map for consumption by downstream SageMaker modules"
  value       = local.sagemaker_root_config
}
```

### Step 12: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 13: Commit and PR

```bash
git add .
git commit -m "Add SageMaker root platform resources"
gh pr create --title "Provision SageMaker root baseline" --body "Adds shared IAM execution role, S3 artifact bucket, optional VPC security group, KMS encryption, and outputs for downstream SageMaker modules"
```

---

## Dependency Guidance

Downstream SageMaker skills consume outputs from this root module:

- **provision-sagemaker-training**: Pass `execution_role_arn` as the training
  execution role, `artifact_bucket_arn` for output artifact storage, and
  `security_group_ids` / `private_subnet_ids` for VPC-mode training.
- **provision-sagemaker-model-registry**: Pass `execution_role_arn` to the
  `allowed_principal_arns` list so the training role can register model packages,
  and use the same `kms_key_arn` for consistent encryption across the pipeline.

Apply this root module before any downstream SageMaker modules.

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Trust only `sagemaker.amazonaws.com` with `aws:SourceAccount` condition | Least-privilege assume-role; blocks cross-account confused deputy |
| S3 IAM scoped to artifact bucket only | No `s3:*` or wildcard bucket access |
| S3 bucket versioning enabled | Protects model artifacts from accidental deletion or overwrites |
| S3 public access fully blocked | Prevents accidental data exposure |
| KMS encryption conditional on `kms_key_arn` | Uses AES256 by default; KMS only when explicitly required |
| VPC security group conditional on `vpc_id` | Only created when VPC-mode SageMaker is needed |
| Security group allows intra-SG traffic only on ingress | Required for distributed training; no open inbound from external |
| VPC policy uses `Resource = "*"` for EC2 network actions | Required by AWS; these EC2 actions do not support resource-level restrictions |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with project, environment, and `ManagedBy` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |
| Outputs consumed by downstream modules | Training and model-registry skills depend on `execution_role_arn`, `artifact_bucket_arn`, `vpc_id`, `security_group_ids` |

---

## Outputs

- Shared IAM execution role trusted by `sagemaker.amazonaws.com` with source account condition
- S3 artifact bucket with versioning, server-side encryption, and public access blocking
- Least-privilege IAM policies: S3 artifacts, CloudWatch Logs, optional KMS, optional VPC networking
- Security group for SageMaker VPC mode with intra-group traffic for distributed training (conditional)
- Terraform outputs for downstream consumption: `execution_role_arn`, `artifact_bucket_arn`, `vpc_id`, `security_group_ids`, `private_subnet_ids`, and full root config map
