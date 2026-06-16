---
name: provision-athena-database
title: Provision Athena Database
type: skill
topics:
  - terraform
  - aws
  - athena
  - infrastructure-as-code
summary: >
  Provision an AWS Athena database and workgroup using Terraform, with a dedicated
  S3 results bucket, Glue catalog database, least-privilege IAM policy, and
  query cost controls.
references:
  - skills/scaffold-terraform-aws-repo.md
  - skills/provision-s3-bucket.md
last-updated: 2026-06-15
---

# Provision Athena Database

Create an Athena workgroup backed by a Glue catalog database with query result
storage, cost controls, and least-privilege IAM. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- S3 bucket exists for source data (the data you will query)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "database_name" {
  description = "Name of the Glue/Athena database"
  type        = string
}

variable "workgroup_name" {
  description = "Name of the Athena workgroup"
  type        = string
}

variable "source_bucket_arn" {
  description = "ARN of the S3 bucket containing source data"
  type        = string
}

variable "results_bucket_name" {
  description = "Name for the S3 bucket that stores query results"
  type        = string
}

variable "bytes_scanned_limit" {
  description = "Max bytes scanned per query (cost control)"
  type        = number
  default     = 10737418240 # 10 GB
}

variable "result_retention_days" {
  description = "Days before query results are expired from the results bucket"
  type        = number
  default     = 30
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
```

### Step 3: Create S3 bucket for query results

```hcl
resource "aws_s3_bucket" "athena_results" {
  bucket = var.results_bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"

    expiration {
      days = var.result_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}
```

### Step 4: Create Glue catalog database

```hcl
resource "aws_glue_catalog_database" "this" {
  name = var.database_name

  tags = var.tags
}
```

### Step 5: Create Athena workgroup

```hcl
resource "aws_athena_workgroup" "this" {
  name = var.workgroup_name

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_limit

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.id}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  tags = var.tags
}
```

### Step 6: Create least-privilege IAM policy

```hcl
resource "aws_iam_policy" "athena_access" {
  name        = "${var.workgroup_name}-athena-access"
  description = "Least-privilege access for Athena workgroup ${var.workgroup_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AthenaQueryAccess"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
        ]
        Resource = "arn:aws:athena:*:${data.aws_caller_identity.current.account_id}:workgroup/${var.workgroup_name}"
      },
      {
        Sid    = "GlueCatalogReadAccess"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
        ]
        Resource = [
          "arn:aws:glue:*:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:*:${data.aws_caller_identity.current.account_id}:database/${var.database_name}",
          "arn:aws:glue:*:${data.aws_caller_identity.current.account_id}:table/${var.database_name}/*",
        ]
      },
      {
        Sid    = "SourceBucketReadAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          var.source_bucket_arn,
          "${var.source_bucket_arn}/*",
        ]
      },
      {
        Sid    = "ResultsBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:GetBucketLocation",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.athena_results.arn,
          "${aws_s3_bucket.athena_results.arn}/*",
        ]
      },
    ]
  })

  tags = var.tags
}
```

### Step 7: Attach policy to workload IAM role

```hcl
variable "workload_role_name" {
  description = "Name of the IAM role that runs Athena queries"
  type        = string
}

resource "aws_iam_role_policy_attachment" "athena_access" {
  role       = var.workload_role_name
  policy_arn = aws_iam_policy.athena_access.arn
}
```

### Step 8: Define outputs

```hcl
output "database_name" {
  description = "Glue catalog database name"
  value       = aws_glue_catalog_database.this.name
}

output "workgroup_name" {
  description = "Athena workgroup name"
  value       = aws_athena_workgroup.this.name
}

output "results_bucket_arn" {
  description = "ARN of the query results S3 bucket"
  value       = aws_s3_bucket.athena_results.arn
}

output "iam_policy_arn" {
  description = "ARN of the Athena access IAM policy"
  value       = aws_iam_policy.athena_access.arn
}
```

### Step 9: Format, commit, and PR

```bash
terraform fmt -recursive
git add .
git commit -m "Add Athena database and workgroup"
gh pr create --title "Provision Athena database" --body "Adds Athena workgroup, Glue catalog DB, results bucket, and IAM policy"
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| No hard-coded secrets or account IDs | Use `data.aws_caller_identity` for account reference |
| Workgroup enforces result location | `enforce_workgroup_configuration = true` prevents users writing results elsewhere |
| Results bucket blocks public access | `aws_s3_bucket_public_access_block` on results bucket |
| Encryption at rest on results bucket | SSE-S3 minimum via `aws_s3_bucket_server_side_encryption_configuration` |
| IAM follows least privilege | No `athena:*` wildcards; scoped to specific workgroup, database, and buckets |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- S3 bucket for query results (versioned, encrypted, lifecycle-managed, public access blocked)
- Glue catalog database (Athena metastore)
- Athena workgroup with cost controls, enforced result location, CloudWatch metrics
- IAM policy with least-privilege Athena, Glue, and S3 permissions
- Policy attached to workload IAM role
