---
name: provision-eventbridge-scheduler
title: Provision EventBridge Scheduler
type: skill
topics:
  - terraform
  - aws
  - eventbridge
  - scheduler
  - infrastructure-as-code
summary: >
  Provision an AWS EventBridge Scheduler schedule using Terraform with a dedicated
  IAM role, least-privilege invoke policy scoped to the target ARN, optional dead
  letter queue, and configurable retry policy.
references:
  - skills/scaffold-terraform-aws-repo.md
last-updated: 2026-06-25
---

# Provision EventBridge Scheduler

Create an EventBridge Scheduler schedule with an IAM execution role, retry
policy, and optional DLQ. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- Target resource exists (Lambda function, Step Functions state machine, etc.)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "schedule_name" {
  description = "Name of the EventBridge Scheduler schedule"
  type        = string
}

variable "schedule_expression" {
  description = "Schedule expression (rate or cron). Examples: rate(1 hour), cron(0 9 * * ? *)"
  type        = string
}

variable "schedule_expression_timezone" {
  description = "IANA timezone for the schedule expression"
  type        = string
  default     = "UTC"
}

variable "schedule_state" {
  description = "Whether the schedule is ENABLED or DISABLED"
  type        = string
  default     = "ENABLED"

  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.schedule_state)
    error_message = "schedule_state must be ENABLED or DISABLED."
  }
}

variable "target_arn" {
  description = "ARN of the target resource (Lambda function, Step Functions state machine, etc.)"
  type        = string
}

variable "target_role_name" {
  description = "Name for the IAM role that Scheduler assumes to invoke the target"
  type        = string
}

variable "input_json" {
  description = "JSON string passed to the target on each invocation"
  type        = string
  default     = "{}"

  validation {
    condition     = can(jsondecode(var.input_json))
    error_message = "input_json must be valid JSON."
  }
}

variable "retry_max_attempts" {
  description = "Maximum number of retry attempts on failure"
  type        = number
  default     = 2
}

variable "retry_max_event_age_seconds" {
  description = "Maximum age in seconds that Scheduler keeps an unprocessed event before discarding"
  type        = number
  default     = 3600
}

variable "dead_letter_queue_arn" {
  description = "ARN of the SQS DLQ for failed invocations (empty string to disable)"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region for the schedule"
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

### Step 3: Create IAM role for Scheduler

```hcl
resource "aws_iam_role" "scheduler" {
  name = var.target_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SchedulerAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
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

### Step 4: Create least-privilege invoke policy

```hcl
resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "${var.target_role_name}-invoke"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeTarget"
        Effect   = "Allow"
        Action   = local.invoke_actions
        Resource = var.target_arn
      },
    ]
  })
}

locals {
  is_step_functions = can(regex("^arn:aws:states:", var.target_arn))
  is_lambda         = can(regex("^arn:aws:lambda:", var.target_arn))

  invoke_actions = (
    local.is_step_functions ? ["states:StartExecution"] :
    local.is_lambda ? ["lambda:InvokeFunction"] :
    ["lambda:InvokeFunction"]
  )
}
```

### Step 5: Attach DLQ policy (conditional)

```hcl
resource "aws_iam_role_policy" "scheduler_dlq" {
  count = var.dead_letter_queue_arn != "" ? 1 : 0
  name  = "${var.target_role_name}-dlq"
  role  = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SendToDLQ"
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = var.dead_letter_queue_arn
      },
    ]
  })
}
```

### Step 6: Create the schedule

```hcl
resource "aws_scheduler_schedule" "this" {
  name       = var.schedule_name
  group_name = "default"
  state      = var.schedule_state

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_expression_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.target_arn
    role_arn = aws_iam_role.scheduler.arn
    input    = var.input_json

    retry_policy {
      maximum_retry_attempts       = var.retry_max_attempts
      maximum_event_age_in_seconds = var.retry_max_event_age_seconds
    }

    dynamic "dead_letter_config" {
      for_each = var.dead_letter_queue_arn != "" ? [1] : []
      content {
        arn = var.dead_letter_queue_arn
      }
    }
  }
}
```

### Step 7: Define outputs

```hcl
output "schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule"
  value       = aws_scheduler_schedule.this.arn
}

output "scheduler_role_arn" {
  description = "ARN of the IAM role used by the scheduler"
  value       = aws_iam_role.scheduler.arn
}

output "target_arn" {
  description = "ARN of the invocation target"
  value       = var.target_arn
}
```

### Step 8: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 9: Commit and PR

```bash
git add .
git commit -m "Add EventBridge Scheduler schedule"
gh pr create --title "Provision EventBridge Scheduler" --body "Adds Scheduler schedule, IAM role, invoke policy, optional DLQ, and retry config"
```

---

## Examples

### Lambda target

```hcl
module "scheduler" {
  source = "./modules/eventbridge-scheduler"

  schedule_name                = "nightly-cleanup"
  schedule_expression          = "cron(0 3 * * ? *)"
  schedule_expression_timezone = "America/New_York"
  schedule_state               = "ENABLED"
  target_arn                   = aws_lambda_function.cleanup.arn
  target_role_name             = "nightly-cleanup-scheduler-role"
  input_json                   = jsonencode({ mode = "full" })
  environment                  = "prod"
  region                       = "us-east-1"
  tags                         = { Team = "platform" }
}
```

### Step Functions target

```hcl
module "scheduler" {
  source = "./modules/eventbridge-scheduler"

  schedule_name                = "hourly-pipeline"
  schedule_expression          = "rate(1 hour)"
  schedule_expression_timezone = "UTC"
  schedule_state               = "ENABLED"
  target_arn                   = aws_sfn_state_machine.pipeline.arn
  target_role_name             = "hourly-pipeline-scheduler-role"
  input_json                   = jsonencode({ source = "scheduler" })
  dead_letter_queue_arn        = aws_sqs_queue.dlq.arn
  environment                  = "prod"
  region                       = "us-east-1"
  tags                         = { Team = "data" }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Use `aws_scheduler_schedule` (not `aws_cloudwatch_event_rule`) | Scheduler API supports timezone, flexible windows, and universal targets |
| Flexible time window OFF by default | Ensures exact execution timing; enable explicitly if jitter acceptable |
| Trust only `scheduler.amazonaws.com` | Scoped assume-role with `aws:SourceAccount` condition prevents confused deputy |
| Invoke policy scoped to target ARN only | No wildcard actions; only `lambda:InvokeFunction` or `states:StartExecution` |
| `input_json` validated as valid JSON | Prevents runtime failures from malformed payloads |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- EventBridge Scheduler schedule with configurable cron/rate expression and timezone
- IAM role trusted by `scheduler.amazonaws.com` with source account condition
- Least-privilege invoke policy scoped to target ARN (Lambda or Step Functions)
- Optional DLQ configuration with SQS send permission
- Configurable retry policy (max attempts and max event age)
- Schedule ARN, scheduler role ARN, and target ARN exported
