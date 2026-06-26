---
name: provision-sns-topic
title: Provision SNS Topic
type: skill
topics:
  - terraform
  - aws
  - sns
  - messaging
  - infrastructure-as-code
summary: >
  Provision an AWS SNS topic using Terraform with optional KMS encryption at rest,
  least-privilege topic policy for approved publishers and subscribers, optional
  subscriptions with delivery policy wiring, and FIFO topic support.
references:
  - skills/scaffold-terraform-aws-repo.md
last-updated: 2026-06-25
---

# Provision SNS Topic

Create an SNS topic with a least-privilege access policy, optional KMS encryption,
optional subscriptions, and FIFO support. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- KMS key exists if encryption is required
- Subscriber endpoints exist (Lambda ARNs, SQS ARNs, email addresses, etc.)
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "topic_name" {
  description = "Name of the SNS topic. FIFO topics must end with .fifo"
  type        = string
}

variable "fifo_topic" {
  description = "Whether the topic is a FIFO topic"
  type        = bool
  default     = false
}

variable "content_based_deduplication" {
  description = "Enable content-based deduplication (FIFO topics only)"
  type        = bool
  default     = false
}

variable "kms_master_key_id" {
  description = "KMS key ID or alias ARN for at-rest encryption (empty string to disable)"
  type        = string
  default     = ""
}

variable "allowed_publisher_arns" {
  description = "List of IAM principal ARNs allowed to publish to the topic"
  type        = list(string)
  default     = []
}

variable "allowed_subscriber_endpoints" {
  description = "List of ARNs or endpoints allowed to subscribe to the topic"
  type        = list(string)
  default     = []
}

variable "delivery_policy_json" {
  description = "JSON string for the HTTP/S delivery policy (empty string to skip)"
  type        = string
  default     = ""

  validation {
    condition     = var.delivery_policy_json == "" || can(jsondecode(var.delivery_policy_json))
    error_message = "delivery_policy_json must be valid JSON or an empty string."
  }
}

variable "subscription_protocols" {
  description = "List of protocols for subscriptions (sqs, lambda, email, https, etc.)"
  type        = list(string)
  default     = []
}

variable "subscription_endpoints" {
  description = "List of endpoints for subscriptions (must match subscription_protocols by index)"
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
  description = "AWS region for the topic"
  type        = string
}
```

### Step 2: Add data sources and locals

```hcl
data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  topic_arn  = aws_sns_topic.this.arn

  subscription_count = min(
    length(var.subscription_protocols),
    length(var.subscription_endpoints)
  )

  subscriptions = [
    for i in range(local.subscription_count) : {
      protocol = var.subscription_protocols[i]
      endpoint = var.subscription_endpoints[i]
    }
  ]
}
```

### Step 3: Create the SNS topic

```hcl
resource "aws_sns_topic" "this" {
  name                        = var.topic_name
  fifo_topic                  = var.fifo_topic
  content_based_deduplication = var.fifo_topic ? var.content_based_deduplication : false
  kms_master_key_id           = var.kms_master_key_id != "" ? var.kms_master_key_id : null

  delivery_policy = var.delivery_policy_json != "" ? var.delivery_policy_json : null

  tags = var.tags
}
```

### Step 4: Create least-privilege topic policy

```hcl
resource "aws_sns_topic_policy" "this" {
  arn = aws_sns_topic.this.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "${var.topic_name}-policy"
    Statement = concat(
      [
        {
          Sid    = "AllowOwnerFullControl"
          Effect = "Allow"
          Principal = {
            AWS = "arn:aws:iam::${local.account_id}:root"
          }
          Action   = "SNS:*"
          Resource = aws_sns_topic.this.arn
        },
      ],
      length(var.allowed_publisher_arns) > 0 ? [
        {
          Sid    = "AllowApprovedPublishers"
          Effect = "Allow"
          Principal = {
            AWS = var.allowed_publisher_arns
          }
          Action   = "SNS:Publish"
          Resource = aws_sns_topic.this.arn
        },
      ] : [],
      length(var.allowed_subscriber_endpoints) > 0 ? [
        {
          Sid    = "AllowApprovedSubscribers"
          Effect = "Allow"
          Principal = {
            AWS = var.allowed_subscriber_endpoints
          }
          Action = [
            "SNS:Subscribe",
            "SNS:Receive",
          ]
          Resource = aws_sns_topic.this.arn
        },
      ] : [],
    )
  })
}
```

### Step 5: Create subscriptions (conditional)

```hcl
resource "aws_sns_topic_subscription" "this" {
  count     = local.subscription_count
  topic_arn = aws_sns_topic.this.arn
  protocol  = local.subscriptions[count.index].protocol
  endpoint  = local.subscriptions[count.index].endpoint
}
```

### Step 6: Define outputs

```hcl
output "topic_arn" {
  description = "ARN of the SNS topic"
  value       = aws_sns_topic.this.arn
}

output "topic_name" {
  description = "Name of the SNS topic"
  value       = aws_sns_topic.this.name
}
```

### Step 7: Format, initialize, and plan

```bash
terraform fmt -recursive
terraform init
terraform plan
```

### Step 8: Commit and PR

```bash
git add .
git commit -m "Add SNS topic with access policy and subscriptions"
gh pr create --title "Provision SNS topic" --body "Adds SNS topic, least-privilege topic policy, optional KMS encryption, optional subscriptions, and FIFO support"
```

---

## Examples

### Standard topic with KMS encryption and Lambda subscriber

```hcl
module "order_notifications" {
  source = "./modules/sns-topic"

  topic_name         = "order-notifications"
  fifo_topic         = false
  kms_master_key_id  = aws_kms_key.sns.arn
  environment        = "prod"
  region             = "us-east-1"

  allowed_publisher_arns = [
    aws_iam_role.order_service.arn,
  ]

  subscription_protocols = ["lambda"]
  subscription_endpoints = [aws_lambda_function.notify.arn]

  tags = { Team = "commerce" }
}
```

### FIFO topic with SQS subscription

```hcl
module "payment_events" {
  source = "./modules/sns-topic"

  topic_name                  = "payment-events.fifo"
  fifo_topic                  = true
  content_based_deduplication = true
  kms_master_key_id           = aws_kms_key.sns.arn
  environment                 = "prod"
  region                      = "us-east-1"

  allowed_publisher_arns = [
    aws_iam_role.payment_service.arn,
  ]

  allowed_subscriber_endpoints = [
    aws_iam_role.ledger_service.arn,
  ]

  subscription_protocols = ["sqs"]
  subscription_endpoints = [aws_sqs_queue.ledger_events.arn]

  tags = { Team = "payments" }
}
```

### HTTP/S delivery policy with email subscriptions

```hcl
module "alert_topic" {
  source = "./modules/sns-topic"

  topic_name  = "system-alerts"
  environment = "prod"
  region      = "us-east-1"

  delivery_policy_json = jsonencode({
    http = {
      defaultHealthyRetryPolicy = {
        minDelayTarget     = 20
        maxDelayTarget     = 20
        numRetries         = 3
        numMaxDelayRetries = 0
        backoffFunction    = "linear"
      }
      disableSubscriptionOverrides = false
    }
  })

  subscription_protocols = ["email", "email"]
  subscription_endpoints = ["oncall@example.com", "backup@example.com"]

  tags = { Team = "sre" }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Topic policy grants only `SNS:Publish` to approved publishers | Least privilege; no wildcard principal access |
| Subscriber policy grants only `SNS:Subscribe` and `SNS:Receive` | Prevents unauthorized subscriptions or topic management |
| `content_based_deduplication` only when `fifo_topic = true` | Setting ignored on standard topics; forced to false to prevent confusion |
| KMS encryption applied only when `kms_master_key_id` is non-empty | Allows opt-in encryption at rest without requiring KMS for every topic |
| `delivery_policy_json` validated as valid JSON | Prevents runtime failures from malformed policy documents |
| `subscription_protocols` and `subscription_endpoints` paired by index | Ensures each subscription has exactly one protocol and one endpoint |
| No secrets in `.tf` or `.tfvars` | Use Secrets Manager or SSM Parameter Store for sensitive values |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- SNS topic (standard or FIFO) with optional content-based deduplication
- Optional KMS encryption at rest via `kms_master_key_id`
- Least-privilege topic policy scoped to approved publisher and subscriber ARNs
- Optional subscriptions wired by protocol and endpoint pairs
- Optional HTTP/S delivery policy with retry configuration
- Topic ARN and topic name exported
