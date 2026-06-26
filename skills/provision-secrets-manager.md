---
name: provision-secrets-manager
title: Provision AWS Secrets Manager Secret
type: skill
topics:
  - terraform
  - aws
  - secrets-manager
  - infrastructure-as-code
  - security
summary: >
  Provision an AWS Secrets Manager secret using Terraform with optional
  customer-managed KMS encryption, least-privilege IAM access for approved
  readers and writers, optional secret resource policy, and rotation wiring.
references:
  - skills/scaffold-terraform-aws-repo.md
last-updated: 2026-06-25
---

# Provision AWS Secrets Manager Secret

Create a Secrets Manager secret with optional KMS encryption, IAM access
policy, secret resource policy, and rotation configuration. Follow steps in
order. Never commit secret values in `.tf` or `.tfvars`.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)
- If using KMS: customer-managed KMS key already provisioned
- If enabling rotation: Lambda rotation function already deployed

---

## Steps

### Step 1: Define variables

```hcl
variable "secret_name" {
  description = "Name of the Secrets Manager secret"
  type        = string
}

variable "secret_description" {
  description = "Human-readable description of the secret"
  type        = string
  default     = ""
}

variable "kms_key_id" {
  description = "ARN or ID of a customer-managed KMS key (empty string for AWS-managed default)"
  type        = string
  default     = ""
}

variable "recovery_window_in_days" {
  description = "Number of days before a deleted secret is permanently removed (0 for immediate, 7-30 otherwise)"
  type        = number
  default     = 30

  validation {
    condition     = var.recovery_window_in_days == 0 || (var.recovery_window_in_days >= 7 && var.recovery_window_in_days <= 30)
    error_message = "recovery_window_in_days must be 0 (immediate) or between 7 and 30."
  }
}

variable "secret_policy_json" {
  description = "JSON string for the secret resource policy (empty string to skip)"
  type        = string
  default     = ""

  validation {
    condition     = var.secret_policy_json == "" || can(jsondecode(var.secret_policy_json))
    error_message = "secret_policy_json must be empty or valid JSON."
  }
}

variable "allowed_principal_arns" {
  description = "List of IAM principal ARNs allowed to read and write the secret"
  type        = list(string)
  default     = []
}

variable "enable_rotation" {
  description = "Enable automatic secret rotation"
  type        = bool
  default     = false
}

variable "rotation_lambda_arn" {
  description = "ARN of the Lambda function that performs rotation (required when enable_rotation is true)"
  type        = string
  default     = ""
}

variable "rotation_days" {
  description = "Number of days between automatic rotations"
  type        = number
  default     = 30
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
  description = "AWS region for the secret"
  type        = string
}
```

### Step 2: Add data sources and validation locals

```hcl
data "aws_caller_identity" "current" {}

locals {
  use_kms_key       = var.kms_key_id != ""
  use_secret_policy = var.secret_policy_json != ""
  has_principals    = length(var.allowed_principal_arns) > 0
}
```

### Step 3: Create the secret

```hcl
resource "aws_secretsmanager_secret" "this" {
  name                    = var.secret_name
  description             = var.secret_description
  kms_key_id              = local.use_kms_key ? var.kms_key_id : null
  recovery_window_in_days = var.recovery_window_in_days

  tags = var.tags
}
```

### Step 4: Attach secret resource policy (conditional)

```hcl
resource "aws_secretsmanager_secret_policy" "this" {
  count      = local.use_secret_policy ? 1 : 0
  secret_arn = aws_secretsmanager_secret.this.arn
  policy     = var.secret_policy_json
}
```

### Step 5: Create IAM policy for approved readers/writers

```hcl
resource "aws_iam_policy" "secret_read" {
  count       = local.has_principals ? 1 : 0
  name        = "${var.secret_name}-read"
  description = "Read access to secret ${var.secret_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GetSecretValue"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = aws_secretsmanager_secret.this.arn
      },
    ]
  })

  tags = var.tags
}

resource "aws_iam_policy" "secret_write" {
  count       = local.has_principals ? 1 : 0
  name        = "${var.secret_name}-write"
  description = "Write access to secret ${var.secret_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PutSecretValue"
        Effect = "Allow"
        Action = [
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecret",
        ]
        Resource = aws_secretsmanager_secret.this.arn
      },
    ]
  })

  tags = var.tags
}
```

### Step 6: Attach policies to approved principals

```hcl
resource "aws_iam_policy_attachment" "secret_read" {
  count      = local.has_principals ? 1 : 0
  name       = "${var.secret_name}-read-attachment"
  policy_arn = aws_iam_policy.secret_read[0].arn
  roles      = [for arn in var.allowed_principal_arns : element(split("/", arn), length(split("/", arn)) - 1)]
}

resource "aws_iam_policy_attachment" "secret_write" {
  count      = local.has_principals ? 1 : 0
  name       = "${var.secret_name}-write-attachment"
  policy_arn = aws_iam_policy.secret_write[0].arn
  roles      = [for arn in var.allowed_principal_arns : element(split("/", arn), length(split("/", arn)) - 1)]
}
```

### Step 7: Add KMS decrypt permission for readers (conditional)

```hcl
resource "aws_iam_policy" "secret_kms_decrypt" {
  count       = local.use_kms_key && local.has_principals ? 1 : 0
  name        = "${var.secret_name}-kms-decrypt"
  description = "KMS decrypt for secret ${var.secret_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
        ]
        Resource = var.kms_key_id
      },
    ]
  })

  tags = var.tags
}

resource "aws_iam_policy_attachment" "secret_kms_decrypt" {
  count      = local.use_kms_key && local.has_principals ? 1 : 0
  name       = "${var.secret_name}-kms-decrypt-attachment"
  policy_arn = aws_iam_policy.secret_kms_decrypt[0].arn
  roles      = [for arn in var.allowed_principal_arns : element(split("/", arn), length(split("/", arn)) - 1)]
}
```

### Step 8: Configure rotation (conditional)

```hcl
resource "aws_secretsmanager_secret_rotation" "this" {
  count               = var.enable_rotation ? 1 : 0
  secret_id           = aws_secretsmanager_secret.this.id
  rotation_lambda_arn = var.rotation_lambda_arn

  rotation_rules {
    automatically_after_days = var.rotation_days
  }
}

resource "aws_lambda_permission" "secrets_manager" {
  count         = var.enable_rotation ? 1 : 0
  statement_id  = "AllowSecretsManagerInvoke-${var.secret_name}"
  action        = "lambda:InvokeFunction"
  function_name = var.rotation_lambda_arn
  principal     = "secretsmanager.amazonaws.com"
  source_arn    = aws_secretsmanager_secret.this.arn
}
```

### Step 9: Define outputs

```hcl
output "secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.this.arn
}

output "secret_name" {
  description = "Name of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.this.name
}

output "kms_key_id" {
  description = "KMS key ID used for encryption (empty if using AWS-managed default)"
  value       = local.use_kms_key ? var.kms_key_id : ""
}
```

### Step 10: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 11: Commit and PR

```bash
git add .
git commit -m "Add Secrets Manager secret"
gh pr create --title "Provision Secrets Manager secret" --body "Adds secret, optional KMS encryption, IAM read/write policies, optional resource policy, and rotation config"
```

---

## Examples

### Minimal secret with default encryption

```hcl
module "api_key" {
  source = "./modules/secrets-manager"

  secret_name        = "myapp/api-key"
  secret_description = "Third-party API key for myapp"
  environment        = "prod"
  region             = "us-east-1"
  tags               = { Team = "platform" }
}
```

### Secret with KMS encryption, IAM access, and rotation

```hcl
module "db_credentials" {
  source = "./modules/secrets-manager"

  secret_name             = "myapp/db-credentials"
  secret_description      = "RDS PostgreSQL credentials for myapp"
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = 7
  environment             = "prod"
  region                  = "us-east-1"

  allowed_principal_arns = [
    aws_iam_role.app_task.arn,
    aws_iam_role.migration_task.arn,
  ]

  enable_rotation     = true
  rotation_lambda_arn = aws_lambda_function.rotate_db_creds.arn
  rotation_days       = 14

  tags = { Team = "data" }
}
```

### Secret with custom resource policy

```hcl
module "shared_secret" {
  source = "./modules/secrets-manager"

  secret_name        = "shared/partner-token"
  secret_description = "Partner integration token shared across accounts"
  environment        = "prod"
  region             = "us-east-1"

  secret_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCrossAccountRead"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::123456789012:root" }
        Action    = "secretsmanager:GetSecretValue"
        Resource  = "*"
      },
    ]
  })

  tags = { Team = "integrations" }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Never commit secret values in `.tf` or `.tfvars` | Terraform manages metadata, policy, and rotation wiring only; values set via CLI or CI pipeline |
| Validate `secret_policy_json` as valid JSON | Prevents runtime failures from malformed policy documents |
| IAM read policy limited to `GetSecretValue` and `DescribeSecret` | Least privilege; no list or admin actions granted |
| IAM write policy limited to `PutSecretValue` and `UpdateSecret` | Writers cannot delete or modify secret metadata |
| KMS decrypt policy only attached when customer KMS key used | Unnecessary for AWS-managed `aws/secretsmanager` default key |
| `rotation_lambda_arn` required only when `enable_rotation = true` | Avoids invalid configuration; rotation needs a deployed Lambda |
| `recovery_window_in_days` validated to 0 or 7-30 | Matches AWS API constraints; 0 means immediate deletion |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- Secrets Manager secret with configurable description and recovery window
- Optional customer-managed KMS encryption with scoped decrypt IAM policy
- Least-privilege IAM read and write policies scoped to the secret ARN
- Optional secret resource policy for cross-account or advanced access control
- Optional rotation configuration with Lambda invoke permission
- Secret ARN, secret name, and KMS key ID exported
