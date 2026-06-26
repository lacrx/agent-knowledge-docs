---
name: provision-s3-bucket
title: Provision S3 Bucket
type: skill
topics:
  - terraform
  - aws
  - s3
  - infrastructure-as-code
summary: >
  Provision an AWS S3 bucket using Terraform with versioning, server-side
  encryption, public access blocking, optional lifecycle rules, access logging,
  and a least-privilege bucket policy scoped to approved principal ARNs.
references:
  - skills/scaffold-terraform-aws-repo.md
last-updated: 2026-06-25
---

# Provision S3 Bucket

Create an S3 bucket with encryption at rest, public access blocking, versioning,
optional lifecycle rules, access logging, and a scoped bucket policy. Follow
steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)
- If access logging is enabled, the target logging bucket must already exist
- Principal ARNs for bucket policy must be valid IAM roles, users, or accounts

---

## Steps

### Step 1: Define variables

```hcl
variable "bucket_name" {
  description = "Globally unique name for the S3 bucket"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be 3-63 characters, lowercase alphanumeric, dots, or hyphens."
  }
}

variable "force_destroy" {
  description = "Allow Terraform to destroy the bucket even if it contains objects"
  type        = bool
  default     = false
}

variable "versioning_enabled" {
  description = "Enable versioning on the bucket"
  type        = bool
  default     = true
}

variable "sse_algorithm" {
  description = "Server-side encryption algorithm (aws:kms or AES256)"
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["aws:kms", "AES256"], var.sse_algorithm)
    error_message = "sse_algorithm must be aws:kms or AES256."
  }
}

variable "kms_key_arn" {
  description = "ARN of the KMS key for SSE-KMS encryption (required when sse_algorithm is aws:kms)"
  type        = string
  default     = ""
}

variable "block_public_acls" {
  description = "Block public ACLs on the bucket"
  type        = bool
  default     = true
}

variable "block_public_policy" {
  description = "Block public bucket policies"
  type        = bool
  default     = true
}

variable "ignore_public_acls" {
  description = "Ignore public ACLs on the bucket"
  type        = bool
  default     = true
}

variable "restrict_public_buckets" {
  description = "Restrict public bucket policies"
  type        = bool
  default     = true
}

variable "lifecycle_rules" {
  description = "List of lifecycle rule objects. Each must have id (string), enabled (bool), and at least one of expiration_days (number) or transition (object with days and storage_class)."
  type = list(object({
    id              = string
    enabled         = bool
    prefix          = optional(string, "")
    expiration_days = optional(number, 0)
    transition = optional(object({
      days          = number
      storage_class = string
    }), null)
  }))
  default = []

  validation {
    condition = alltrue([
      for rule in var.lifecycle_rules :
      rule.expiration_days > 0 || rule.transition != null
    ])
    error_message = "Each lifecycle rule must have expiration_days > 0 or a transition block."
  }
}

variable "access_logging_bucket" {
  description = "Name of the S3 bucket to receive access logs (empty string to disable)"
  type        = string
  default     = ""
}

variable "access_logging_prefix" {
  description = "Prefix for access log objects in the logging bucket"
  type        = string
  default     = ""
}

variable "allowed_principal_arns" {
  description = "List of IAM principal ARNs allowed to read and write objects in the bucket"
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
  description = "AWS region for the bucket"
  type        = string
}
```

### Step 2: Add data sources

```hcl
data "aws_caller_identity" "current" {}
```

### Step 3: Create the S3 bucket

```hcl
resource "aws_s3_bucket" "this" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy
  tags          = var.tags
}
```

### Step 4: Configure versioning

```hcl
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Suspended"
  }
}
```

### Step 5: Configure server-side encryption

```hcl
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_algorithm
      kms_master_key_id = var.sse_algorithm == "aws:kms" ? var.kms_key_arn : null
    }
    bucket_key_enabled = var.sse_algorithm == "aws:kms" ? true : false
  }
}
```

### Step 6: Block public access

```hcl
resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = var.block_public_acls
  block_public_policy     = var.block_public_policy
  ignore_public_acls      = var.ignore_public_acls
  restrict_public_buckets = var.restrict_public_buckets
}
```

### Step 7: Configure lifecycle rules (conditional)

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count  = length(var.lifecycle_rules) > 0 ? 1 : 0
  bucket = aws_s3_bucket.this.id

  dynamic "rule" {
    for_each = var.lifecycle_rules
    content {
      id     = rule.value.id
      status = rule.value.enabled ? "Enabled" : "Disabled"

      filter {
        prefix = rule.value.prefix
      }

      dynamic "expiration" {
        for_each = rule.value.expiration_days > 0 ? [1] : []
        content {
          days = rule.value.expiration_days
        }
      }

      dynamic "transition" {
        for_each = rule.value.transition != null ? [rule.value.transition] : []
        content {
          days          = transition.value.days
          storage_class = transition.value.storage_class
        }
      }
    }
  }
}
```

### Step 8: Configure access logging (conditional)

```hcl
resource "aws_s3_bucket_logging" "this" {
  count  = var.access_logging_bucket != "" ? 1 : 0
  bucket = aws_s3_bucket.this.id

  target_bucket = var.access_logging_bucket
  target_prefix = var.access_logging_prefix
}
```

### Step 9: Attach bucket policy for approved principals (conditional)

```hcl
resource "aws_s3_bucket_policy" "this" {
  count  = length(var.allowed_principal_arns) > 0 ? 1 : 0
  bucket = aws_s3_bucket.this.id

  depends_on = [aws_s3_bucket_public_access_block.this]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowApprovedPrincipals"
        Effect = "Allow"
        Principal = {
          AWS = var.allowed_principal_arns
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject",
        ]
        Resource = [
          aws_s3_bucket.this.arn,
          "${aws_s3_bucket.this.arn}/*",
        ]
      },
      {
        Sid       = "DenyUnencryptedTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.this.arn,
          "${aws_s3_bucket.this.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })
}
```

### Step 10: Define outputs

```hcl
output "bucket_id" {
  description = "Name (ID) of the S3 bucket"
  value       = aws_s3_bucket.this.id
}

output "bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.this.arn
}

output "bucket_domain_name" {
  description = "Bucket domain name (e.g. bucket-name.s3.amazonaws.com)"
  value       = aws_s3_bucket.this.bucket_domain_name
}
```

### Step 11: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 12: Commit and PR

```bash
git add .
git commit -m "Add S3 bucket with encryption, versioning, and access controls"
gh pr create --title "Provision S3 bucket" --body "Adds S3 bucket with SSE encryption, versioning, public access blocking, optional lifecycle rules, access logging, and least-privilege bucket policy"
```

---

## Examples

### Basic encrypted bucket with versioning

```hcl
module "data_bucket" {
  source = "./modules/s3-bucket"

  bucket_name        = "myorg-data-prod-us-east-1"
  versioning_enabled = true
  sse_algorithm      = "AES256"
  environment        = "prod"
  region             = "us-east-1"
  tags               = { Team = "platform" }
}
```

### KMS-encrypted bucket with lifecycle rules and logging

```hcl
module "logs_bucket" {
  source = "./modules/s3-bucket"

  bucket_name        = "myorg-app-logs-prod-us-east-1"
  versioning_enabled = true
  sse_algorithm      = "aws:kms"
  kms_key_arn        = aws_kms_key.s3.arn
  environment        = "prod"
  region             = "us-east-1"

  lifecycle_rules = [
    {
      id              = "transition-to-ia"
      enabled         = true
      prefix          = ""
      expiration_days = 0
      transition = {
        days          = 30
        storage_class = "STANDARD_IA"
      }
    },
    {
      id              = "expire-old-logs"
      enabled         = true
      prefix          = "logs/"
      expiration_days = 90
      transition      = null
    },
  ]

  access_logging_bucket = "myorg-access-logs-prod-us-east-1"
  access_logging_prefix = "s3/app-logs/"

  allowed_principal_arns = [
    "arn:aws:iam::123456789012:role/app-writer-role",
    "arn:aws:iam::123456789012:role/analytics-reader-role",
  ]

  tags = { Team = "data", CostCenter = "analytics" }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Encryption at rest enabled by default (AES256) | Meets compliance requirements; all objects encrypted without extra config |
| Public access blocked by default (all four flags true) | Prevents accidental data exposure; override explicitly per flag if needed |
| Bucket policy denies unencrypted transport | Enforces TLS for all S3 API calls via `aws:SecureTransport` condition |
| Bucket policy scoped to explicit principal ARNs only | No wildcard principals; least-privilege access for approved roles only |
| Globally unique bucket name validated by regex | Prevents creation failures from invalid naming; enforces DNS-compatible names |
| `lifecycle_rules` validated before use | Each rule must have `expiration_days > 0` or a `transition` block to avoid no-op rules |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- S3 bucket with globally unique name and configurable force-destroy
- Versioning enabled or suspended via variable toggle
- Server-side encryption (AES256 or SSE-KMS with optional KMS key and bucket key)
- Public access block with all four flags defaulting to true
- Optional lifecycle rules with expiration and storage class transitions
- Optional access logging to a separate S3 bucket with configurable prefix
- Least-privilege bucket policy scoped to approved IAM principal ARNs
- TLS-only transport enforced via bucket policy deny condition
- Bucket ID, bucket ARN, and bucket domain name exported
