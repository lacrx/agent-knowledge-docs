---
name: provision-lambda-function
title: Provision AWS Lambda Function
type: skill
topics:
  - terraform
  - aws
  - lambda
  - serverless
  - infrastructure-as-code
summary: >
  Provision an AWS Lambda function using Terraform with IAM execution role,
  least-privilege permissions, CloudWatch log group with configurable retention,
  support for zip-based or container image deployment, optional environment
  variables, optional VPC attachment, and event source wiring guidance.
references:
  - skills/scaffold-terraform-aws-repo.md
last-updated: 2026-06-25
---

# Provision AWS Lambda Function

Create a Lambda function with an IAM execution role, CloudWatch logging,
and configurable deployment packaging. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- Function code packaged as a zip archive (local path or S3) or a container image pushed to ECR
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "runtime" {
  description = "Lambda runtime (e.g. python3.12, nodejs20.x). Set to null for image-based deployments."
  type        = string
  default     = null
}

variable "handler" {
  description = "Function entrypoint (e.g. app.handler). Set to null for image-based deployments."
  type        = string
  default     = null
}

variable "source_path" {
  description = "Local path to the zip archive. Mutually exclusive with s3_bucket/s3_key and image_uri."
  type        = string
  default     = null
}

variable "s3_bucket" {
  description = "S3 bucket containing the deployment package"
  type        = string
  default     = null
}

variable "s3_key" {
  description = "S3 object key for the deployment package"
  type        = string
  default     = null
}

variable "image_uri" {
  description = "ECR image URI for container-based deployment. Mutually exclusive with zip-based variables."
  type        = string
  default     = null
}

variable "role_name" {
  description = "Name for the Lambda IAM execution role"
  type        = string
}

variable "memory_size" {
  description = "Amount of memory in MB allocated to the function"
  type        = number
  default     = 128
}

variable "timeout" {
  description = "Function timeout in seconds"
  type        = number
  default     = 30
}

variable "architectures" {
  description = "Instruction set architecture (x86_64 or arm64)"
  type        = list(string)
  default     = ["x86_64"]

  validation {
    condition     = alltrue([for a in var.architectures : contains(["x86_64", "arm64"], a)])
    error_message = "architectures must contain only x86_64 or arm64."
  }
}

variable "environment_variables" {
  description = "Map of environment variables for the function. Do not store secrets here; use Secrets Manager or SSM."
  type        = map(string)
  default     = {}
}

variable "subnet_ids" {
  description = "List of subnet IDs for VPC attachment. Leave empty to skip VPC config."
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "List of security group IDs for VPC attachment. Required when subnet_ids is set."
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 14
}

variable "kms_key_arn" {
  description = "ARN of a KMS key for encrypting environment variables at rest. Empty string to use default key."
  type        = string
  default     = ""
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
  description = "AWS region for the Lambda function"
  type        = string
}
```

### Step 2: Add data sources and locals

```hcl
data "aws_caller_identity" "current" {}

locals {
  use_image    = var.image_uri != null
  use_s3       = var.s3_bucket != null && var.s3_key != null
  use_local    = var.source_path != null
  use_vpc      = length(var.subnet_ids) > 0
  package_type = local.use_image ? "Image" : "Zip"
}
```

### Step 3: Create CloudWatch Logs log group

```hcl
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
```

### Step 4: Create IAM execution role

```hcl
resource "aws_iam_role" "lambda" {
  name = var.role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
    ]
  })

  tags = var.tags
}
```

### Step 5: Create CloudWatch Logs policy

```hcl
resource "aws_iam_role_policy" "lambda_logs" {
  name = "${var.role_name}-logs"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WriteLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
      },
    ]
  })
}
```

### Step 6: Create VPC access policy (conditional)

```hcl
resource "aws_iam_role_policy" "lambda_vpc" {
  count = local.use_vpc ? 1 : 0
  name  = "${var.role_name}-vpc"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VPCNetworkInterfaces"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
        ]
        Resource = "*"
      },
    ]
  })
}
```

### Step 7: Create the Lambda function

```hcl
resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = aws_iam_role.lambda.arn
  package_type  = local.package_type
  architectures = var.architectures
  memory_size   = var.memory_size
  timeout       = var.timeout

  # Zip from local file
  filename         = local.use_local ? var.source_path : null
  source_code_hash = local.use_local ? filebase64sha256(var.source_path) : null

  # Zip from S3
  s3_bucket = local.use_s3 ? var.s3_bucket : null
  s3_key    = local.use_s3 ? var.s3_key : null

  # Container image
  image_uri = local.use_image ? var.image_uri : null

  # Runtime and handler are required for Zip, not for Image
  runtime = local.use_image ? null : var.runtime
  handler = local.use_image ? null : var.handler

  # Optional KMS encryption for environment variables
  kms_key_arn = var.kms_key_arn != "" ? var.kms_key_arn : null

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }

  dynamic "vpc_config" {
    for_each = local.use_vpc ? [1] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = var.security_group_ids
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_logs,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = var.tags
}
```

### Step 8: Define outputs

```hcl
output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.this.arn
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.this.function_name
}

output "execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda.arn
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
git commit -m "Add Lambda function infrastructure"
gh pr create --title "Provision Lambda function" --body "Adds Lambda function, IAM execution role, CloudWatch log group, optional VPC attachment, and environment variable support"
```

---

## Examples

### Zip-based deployment from local file

```hcl
module "api_handler" {
  source = "./modules/lambda"

  function_name = "api-handler"
  runtime       = "python3.12"
  handler       = "app.handler"
  source_path   = "${path.module}/dist/api-handler.zip"
  role_name     = "api-handler-lambda-role"
  memory_size   = 256
  timeout       = 30
  architectures = ["arm64"]
  environment   = "prod"
  region        = "us-east-1"

  environment_variables = {
    LOG_LEVEL  = "INFO"
    TABLE_NAME = aws_dynamodb_table.orders.name
  }

  tags = { Team = "platform" }
}
```

### Container image deployment with VPC

```hcl
module "data_processor" {
  source = "./modules/lambda"

  function_name      = "data-processor"
  image_uri          = "${aws_ecr_repository.processor.repository_url}:latest"
  role_name          = "data-processor-lambda-role"
  memory_size        = 1024
  timeout            = 300
  architectures      = ["x86_64"]
  subnet_ids         = data.aws_subnets.private.ids
  security_group_ids = [aws_security_group.lambda.id]
  log_retention_days = 30
  environment        = "prod"
  region             = "us-east-1"

  environment_variables = {
    DB_HOST = aws_rds_cluster.main.endpoint
  }

  tags = { Team = "data" }
}
```

### S3-based deployment

```hcl
module "batch_worker" {
  source = "./modules/lambda"

  function_name = "batch-worker"
  runtime       = "nodejs20.x"
  handler       = "index.handler"
  s3_bucket     = aws_s3_bucket.artifacts.id
  s3_key        = "lambdas/batch-worker/v1.0.0.zip"
  role_name     = "batch-worker-lambda-role"
  memory_size   = 512
  timeout       = 900
  environment   = "prod"
  region        = "us-east-1"

  tags = { Team = "batch" }
}
```

---

## Event Source Wiring Guidance

After provisioning the function, wire event sources with separate resources:

- **API Gateway**: Use `aws_api_gateway_rest_api` or `aws_apigatewayv2_api` with `aws_lambda_permission`.
- **SQS**: Use `aws_lambda_event_source_mapping` with the queue ARN and add `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` to the execution role.
- **S3 notifications**: Use `aws_s3_bucket_notification` with `aws_lambda_permission`.
- **EventBridge**: Use `aws_cloudwatch_event_rule` and `aws_cloudwatch_event_target` with `aws_lambda_permission`.
- **SNS**: Use `aws_sns_topic_subscription` with `aws_lambda_permission`.

Each event source requires a corresponding `aws_lambda_permission` resource granting the source service invoke access.

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Support both `Zip` and `Image` package types | Covers standard zip deployments and container-based workflows without mixing them |
| Least-privilege IAM only | Execution role gets `logs:CreateLogStream` and `logs:PutLogEvents` scoped to the function log group; VPC ENI permissions added only when VPC is enabled |
| Trust only `lambda.amazonaws.com` | Scoped assume-role with `aws:SourceAccount` condition prevents confused deputy |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager, SSM Parameter Store, or KMS-encrypted environment variables |
| `environment_variables` must not contain secrets directly | Source sensitive values from Secrets Manager or SSM at runtime |
| CloudWatch log group created explicitly with retention | Avoids auto-created groups with infinite retention; retention is configurable via `log_retention_days` |
| VPC inputs required only when VPC attachment is enabled | `subnet_ids` and `security_group_ids` are empty by default; VPC policy is conditionally created |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- Lambda function supporting zip-based (local or S3) and container image deployments
- IAM execution role trusted by `lambda.amazonaws.com` with source account condition
- CloudWatch Logs log group with configurable retention period
- Least-privilege log delivery policy scoped to the function log group
- Conditional VPC attachment with ENI management policy
- Optional KMS encryption for environment variables at rest
- `lambda_function_arn`, `lambda_function_name`, and `execution_role_arn` exported
