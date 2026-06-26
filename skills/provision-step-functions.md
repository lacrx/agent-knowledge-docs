---
name: provision-step-functions
title: Provision Step Functions State Machine
type: skill
topics:
  - terraform
  - aws
  - step-functions
  - infrastructure-as-code
summary: >
  Provision an AWS Step Functions state machine using Terraform with an external
  ASL definition file, dedicated IAM role, least-privilege invoke policies scoped
  to target ARNs, CloudWatch Logs execution logging, and optional X-Ray tracing.
references:
  - skills/scaffold-terraform-aws-repo.md
  - skills/provision-eventbridge-scheduler.md
last-updated: 2026-06-25
---

# Provision Step Functions State Machine

Create a Step Functions state machine with IAM execution role, CloudWatch Logs
logging, and least-privilege target policies. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- ASL definition file written (JSON) at a known path relative to the Terraform root
- Target resources exist (Lambda functions, DynamoDB tables, SQS queues, etc.)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "state_machine_name" {
  description = "Name of the Step Functions state machine"
  type        = string
}

variable "state_machine_type" {
  description = "Type of state machine (STANDARD or EXPRESS)"
  type        = string
  default     = "STANDARD"

  validation {
    condition     = contains(["STANDARD", "EXPRESS"], var.state_machine_type)
    error_message = "state_machine_type must be STANDARD or EXPRESS."
  }
}

variable "state_machine_definition_path" {
  description = "Path to the ASL definition JSON file relative to the Terraform root"
  type        = string
}

variable "role_name" {
  description = "Name for the IAM role that Step Functions assumes"
  type        = string
}

variable "log_group_name" {
  description = "Name of the CloudWatch Logs log group for execution logs"
  type        = string
}

variable "log_level" {
  description = "Logging level for execution history (ALL, ERROR, FATAL, OFF)"
  type        = string
  default     = "ALL"

  validation {
    condition     = contains(["ALL", "ERROR", "FATAL", "OFF"], var.log_level)
    error_message = "log_level must be ALL, ERROR, FATAL, or OFF."
  }
}

variable "include_execution_data" {
  description = "Whether to include input/output data in execution logs"
  type        = bool
  default     = true
}

variable "tracing_enabled" {
  description = "Enable X-Ray tracing for the state machine"
  type        = bool
  default     = false
}

variable "target_arns" {
  description = "List of ARNs the state machine invokes (Lambda, DynamoDB, SQS, etc.)"
  type        = list(string)
  default     = []
}

variable "target_actions" {
  description = "List of IAM actions the state machine needs on target resources"
  type        = list(string)
  default     = ["lambda:InvokeFunction"]
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region for the state machine"
  type        = string
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

### Step 3: Create CloudWatch Logs log group

```hcl
resource "aws_cloudwatch_log_group" "sfn" {
  name              = var.log_group_name
  retention_in_days = 30
  tags              = var.tags
}
```

### Step 4: Create IAM role for Step Functions

```hcl
resource "aws_iam_role" "sfn" {
  name = var.role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "StepFunctionsAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
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

### Step 5: Create CloudWatch Logs delivery policy

```hcl
resource "aws_iam_role_policy" "sfn_logs" {
  name = "${var.role_name}-logs"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogsDelivery"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:DescribeLogGroups",
          "logs:DescribeResourcePolicies",
          "logs:GetLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:UpdateLogDelivery",
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsPut"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.sfn.arn}:*"
      },
    ]
  })
}
```

### Step 6: Create X-Ray tracing policy (conditional)

```hcl
resource "aws_iam_role_policy" "sfn_xray" {
  count = var.tracing_enabled ? 1 : 0
  name  = "${var.role_name}-xray"
  role  = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
        ]
        Resource = "*"
      },
    ]
  })
}
```

### Step 7: Create least-privilege target invoke policy

```hcl
resource "aws_iam_role_policy" "sfn_targets" {
  count = length(var.target_arns) > 0 ? 1 : 0
  name  = "${var.role_name}-targets"
  role  = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeTargets"
        Effect   = "Allow"
        Action   = var.target_actions
        Resource = var.target_arns
      },
    ]
  })
}
```

### Step 8: Create the state machine

```hcl
resource "aws_sfn_state_machine" "this" {
  name     = var.state_machine_name
  type     = var.state_machine_type
  role_arn = aws_iam_role.sfn.arn

  definition = file(var.state_machine_definition_path)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    level                  = var.log_level
    include_execution_data = var.include_execution_data
  }

  tracing_configuration {
    enabled = var.tracing_enabled
  }

  tags = var.tags
}
```

### Step 9: Define outputs

```hcl
output "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  value       = aws_sfn_state_machine.this.arn
}

output "role_arn" {
  description = "ARN of the IAM execution role"
  value       = aws_iam_role.sfn.arn
}

output "log_group_arn" {
  description = "ARN of the CloudWatch Logs log group"
  value       = aws_cloudwatch_log_group.sfn.arn
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
git commit -m "Add Step Functions state machine"
gh pr create --title "Provision Step Functions state machine" --body "Adds state machine, IAM role, CloudWatch Logs, target invoke policy, and optional X-Ray tracing"
```

---

## Examples

### Lambda-based workflow

```hcl
module "order_pipeline" {
  source = "./modules/step-functions"

  state_machine_name            = "order-pipeline"
  state_machine_type            = "STANDARD"
  state_machine_definition_path = "${path.module}/definitions/order-pipeline.asl.json"
  role_name                     = "order-pipeline-sfn-role"
  log_group_name                = "/aws/vendedlogs/states/order-pipeline"
  log_level                     = "ALL"
  include_execution_data        = true
  tracing_enabled               = true
  environment                   = "prod"
  region                        = "us-east-1"

  target_arns = [
    aws_lambda_function.validate_order.arn,
    aws_lambda_function.charge_payment.arn,
    aws_lambda_function.send_confirmation.arn,
  ]
  target_actions = ["lambda:InvokeFunction"]

  tags = { Team = "commerce" }
}
```

### Express workflow with DynamoDB and SQS targets

```hcl
module "event_processor" {
  source = "./modules/step-functions"

  state_machine_name            = "event-processor"
  state_machine_type            = "EXPRESS"
  state_machine_definition_path = "${path.module}/definitions/event-processor.asl.json"
  role_name                     = "event-processor-sfn-role"
  log_group_name                = "/aws/vendedlogs/states/event-processor"
  log_level                     = "ERROR"
  include_execution_data        = false
  tracing_enabled               = false
  environment                   = "prod"
  region                        = "us-east-1"

  target_arns = [
    aws_dynamodb_table.events.arn,
    aws_sqs_queue.notifications.arn,
  ]
  target_actions = [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:UpdateItem",
    "sqs:SendMessage",
  ]

  tags = { Team = "platform" }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Use `aws_sfn_state_machine` | Native Terraform resource with full logging and tracing support |
| ASL definition loaded via `file()` from external path | Keeps Terraform clean; ASL is version-controlled separately and avoids large inline JSON |
| Trust only `states.amazonaws.com` | Scoped assume-role with `aws:SourceAccount` condition prevents confused deputy |
| Target invoke policy scoped to exact ARNs | No wildcard resources; actions explicitly listed per target type |
| CloudWatch Logs logging enabled by default | Execution history required for debugging and auditing |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- Step Functions state machine (STANDARD or EXPRESS) with external ASL definition
- IAM role trusted by `states.amazonaws.com` with source account condition
- CloudWatch Logs log group with 30-day retention and execution logging
- Least-privilege invoke policy scoped to specific target ARNs and actions
- Optional X-Ray tracing with scoped IAM policy
- State machine ARN, role ARN, and log group ARN exported
