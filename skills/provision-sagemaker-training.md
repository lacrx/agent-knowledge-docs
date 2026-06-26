---
name: provision-sagemaker-training
title: Provision SageMaker Training Configuration
type: skill
topics:
  - terraform
  - aws
  - sagemaker
  - machine-learning
  - infrastructure-as-code
summary: >
  Provision a reusable SageMaker training configuration using Terraform with a
  dedicated IAM execution role, S3 data/artifact access, optional VPC and KMS
  encryption, and CloudWatch alarms for training capacity usage.
references:
  - skills/scaffold-terraform-aws-repo.md
  - articles/ai-ml/sagemaker-ml-platform.md
last-updated: 2026-06-25
---

# Provision SageMaker Training Configuration

Create a SageMaker training configuration with IAM role, S3 access policies,
optional VPC networking, KMS encryption, and capacity alarms. Follow steps in
order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- S3 buckets exist for training input data and output artifacts
- Training container image pushed to ECR or using a SageMaker built-in image URI
- (Optional) VPC with private subnets and security groups if VPC mode is needed
- (Optional) KMS key created if at-rest encryption is required
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "training_job_name_prefix" {
  description = "Prefix for training job names (used in resource naming)"
  type        = string
}

variable "sagemaker_execution_role_name" {
  description = "Name for the IAM role that SageMaker assumes during training"
  type        = string
}

variable "training_image_uri" {
  description = "ECR image URI or SageMaker built-in algorithm image URI"
  type        = string
}

variable "instance_type" {
  description = "SageMaker training instance type (e.g. ml.m5.xlarge, ml.p3.2xlarge)"
  type        = string
  default     = "ml.m5.xlarge"
}

variable "instance_count" {
  description = "Number of training instances"
  type        = number
  default     = 1
}

variable "volume_size_gb" {
  description = "Size of the EBS volume attached to each training instance (GB)"
  type        = number
  default     = 30
}

variable "max_runtime_seconds" {
  description = "Maximum runtime for a training job before it is stopped"
  type        = number
  default     = 86400
}

variable "input_s3_uri" {
  description = "S3 URI for training input data (e.g. s3://bucket/training-data/)"
  type        = string
}

variable "output_s3_uri" {
  description = "S3 URI for training output artifacts (e.g. s3://bucket/model-artifacts/)"
  type        = string
}

variable "vpc_subnet_ids" {
  description = "List of VPC subnet IDs for training instances (empty to disable VPC mode)"
  type        = list(string)
  default     = []
}

variable "vpc_security_group_ids" {
  description = "List of security group IDs for training instances (empty to disable VPC mode)"
  type        = list(string)
  default     = []
}

variable "kms_key_arn" {
  description = "KMS key ARN for encrypting training volume and output artifacts (empty to use default)"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
```

### Step 2: Add data sources and locals

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  input_bucket_arn  = "arn:aws:s3:::${split("/", replace(var.input_s3_uri, "s3://", ""))[0]}"
  input_prefix      = join("/", slice(split("/", replace(var.input_s3_uri, "s3://", "")), 1, length(split("/", replace(var.input_s3_uri, "s3://", "")))))
  output_bucket_arn = "arn:aws:s3:::${split("/", replace(var.output_s3_uri, "s3://", ""))[0]}"
  output_prefix     = join("/", slice(split("/", replace(var.output_s3_uri, "s3://", "")), 1, length(split("/", replace(var.output_s3_uri, "s3://", "")))))
}
```

### Step 3: Create IAM execution role

```hcl
resource "aws_iam_role" "sagemaker" {
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
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
    ]
  })

  tags = var.tags
}
```

### Step 4: Create S3 access policy (scoped to specific paths)

```hcl
resource "aws_iam_role_policy" "sagemaker_s3" {
  name = "${var.sagemaker_execution_role_name}-s3"
  role = aws_iam_role.sagemaker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadTrainingData"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          local.input_bucket_arn,
          "${local.input_bucket_arn}/${local.input_prefix}*",
        ]
      },
      {
        Sid    = "WriteModelArtifacts"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          local.output_bucket_arn,
          "${local.output_bucket_arn}/${local.output_prefix}*",
        ]
      },
    ]
  })
}
```

### Step 5: Create ECR pull policy

```hcl
resource "aws_iam_role_policy" "sagemaker_ecr" {
  name = "${var.sagemaker_execution_role_name}-ecr"
  role = aws_iam_role.sagemaker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PullTrainingImage"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
    ]
  })
}
```

### Step 6: Create CloudWatch Logs policy

```hcl
resource "aws_iam_role_policy" "sagemaker_logs" {
  name = "${var.sagemaker_execution_role_name}-logs"
  role = aws_iam_role.sagemaker.id

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
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/TrainingJobs:*"
      },
    ]
  })
}
```

### Step 7: Create KMS policy (conditional)

```hcl
resource "aws_iam_role_policy" "sagemaker_kms" {
  count = var.kms_key_arn != "" ? 1 : 0
  name  = "${var.sagemaker_execution_role_name}-kms"
  role  = aws_iam_role.sagemaker.id

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
        ]
        Resource = var.kms_key_arn
      },
    ]
  })
}
```

### Step 8: Create VPC network policy (conditional)

```hcl
resource "aws_iam_role_policy" "sagemaker_vpc" {
  count = length(var.vpc_subnet_ids) > 0 ? 1 : 0
  name  = "${var.sagemaker_execution_role_name}-vpc"
  role  = aws_iam_role.sagemaker.id

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

### Step 9: Create training configuration as a Terraform local for reference

```hcl
locals {
  training_config = {
    name_prefix         = var.training_job_name_prefix
    image_uri           = var.training_image_uri
    instance_type       = var.instance_type
    instance_count      = var.instance_count
    volume_size_gb      = var.volume_size_gb
    max_runtime_seconds = var.max_runtime_seconds
    input_s3_uri        = var.input_s3_uri
    output_s3_uri       = var.output_s3_uri
    execution_role_arn  = aws_iam_role.sagemaker.arn
    kms_key_arn         = var.kms_key_arn
    vpc_subnets         = var.vpc_subnet_ids
    vpc_security_groups = var.vpc_security_group_ids
  }
}
```

### Step 10: Create CloudWatch alarm for training capacity

```hcl
resource "aws_cloudwatch_metric_alarm" "gpu_utilization" {
  alarm_name          = "${var.training_job_name_prefix}-gpu-utilization-low"
  alarm_description   = "Alert when GPU utilization drops below threshold during training"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "GPUUtilization"
  namespace           = "/aws/sagemaker/TrainingJobs"
  period              = 300
  statistic           = "Average"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    Host = "${var.training_job_name_prefix}-*"
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "disk_utilization" {
  alarm_name          = "${var.training_job_name_prefix}-disk-utilization-high"
  alarm_description   = "Alert when disk utilization exceeds threshold during training"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DiskUtilization"
  namespace           = "/aws/sagemaker/TrainingJobs"
  period              = 300
  statistic           = "Average"
  threshold           = 90
  treat_missing_data  = "notBreaching"

  dimensions = {
    Host = "${var.training_job_name_prefix}-*"
  }

  tags = var.tags
}
```

### Step 11: Define outputs

```hcl
output "execution_role_arn" {
  description = "ARN of the SageMaker execution IAM role"
  value       = aws_iam_role.sagemaker.arn
}

output "training_artifact_s3_uri" {
  description = "S3 URI where training artifacts are written"
  value       = var.output_s3_uri
}

output "training_config_name" {
  description = "Training job name prefix for identifying jobs"
  value       = var.training_job_name_prefix
}

output "training_config" {
  description = "Full training configuration map for use by job launchers"
  value       = local.training_config
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
git commit -m "Add SageMaker training configuration"
gh pr create --title "Provision SageMaker training config" --body "Adds SageMaker execution role, S3/ECR/logs/VPC/KMS policies, training config, and capacity alarms"
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| S3 IAM scoped to specific bucket paths | No `s3:*` or bucket-wide wildcards; read on input prefix, write on output prefix |
| ECR `GetAuthorizationToken` on `*` | Required by ECR auth; cannot be scoped to a single repo |
| CloudWatch Logs scoped to `/aws/sagemaker/TrainingJobs` | SageMaker writes to this fixed log group path |
| VPC and KMS policies conditional | Only created when `vpc_subnet_ids` or `kms_key_arn` are provided |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Trust only `sagemaker.amazonaws.com` | Scoped assume-role with `aws:SourceAccount` condition |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |
| Requires baseline S3 and IAM setup | Input/output S3 buckets and ECR repo must exist before applying |

---

## Outputs

- IAM execution role trusted by `sagemaker.amazonaws.com` with source account condition
- Least-privilege policies: S3 (path-scoped), ECR pull, CloudWatch Logs, optional KMS, optional VPC
- Training configuration local for consumption by job launchers (CLI, SDK, or Step Functions)
- CloudWatch alarms for GPU utilization (low) and disk utilization (high)
- Execution role ARN, artifact S3 URI, training config name, and full config map exported
