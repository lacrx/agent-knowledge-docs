---
name: provision-fargate-task
title: Provision ECS Fargate Task Definition
type: skill
topics:
  - terraform
  - aws
  - fargate
  - ecs
  - containers
  - infrastructure-as-code
summary: >
  Provision an ECS Fargate task definition using Terraform with separate execution
  and task IAM roles, container definition with logging, CPU/memory configuration,
  awsvpc networking, optional environment variables, and secret injection from
  Secrets Manager or SSM Parameter Store.
references:
  - skills/scaffold-terraform-aws-repo.md
  - articles/aws/aws-web-app-networking.md
  - articles/aws/fargate/deploying-python-web-apps-to-fargate.md
  - articles/aws/fargate/structuring-fastapi-for-fargate.md
last-updated: 2026-06-25
---

# Provision ECS Fargate Task Definition

Create an ECS Fargate task definition with execution role, task role, container
definition, CloudWatch Logs logging, and optional secrets injection. Follow steps
in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- ECR repository or container image URI available
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)
- Secrets Manager secrets or SSM parameters created if using secret injection

---

## Steps

### Step 1: Define variables

```hcl
variable "task_family" {
  description = "Family name for the ECS task definition"
  type        = string
}
variable "container_name" {
  description = "Name of the container within the task definition"
  type        = string
}
variable "image_uri" {
  description = "Full ECR image URI with tag or digest (e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com/app:sha-abc123)"
  type        = string
}
variable "cpu" {
  description = "CPU units for the task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 256
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.cpu)
    error_message = "cpu must be one of: 256, 512, 1024, 2048, 4096."
  }
}
variable "memory" {
  description = "Memory in MiB for the task (512, 1024, 2048, 4096, 8192, etc.)"
  type        = number
  default     = 512
}
variable "execution_role_name" {
  description = "Name for the IAM execution role (ECS agent: image pull, logs)"
  type        = string
}
variable "task_role_name" {
  description = "Name for the IAM task role (application container runtime)"
  type        = string
}
variable "port_mappings" {
  description = "List of port mappings for the container"
  type        = list(object({ containerPort = number, protocol = optional(string, "tcp") }))
  default     = []
}
variable "environment_variables" {
  description = "Non-sensitive environment variables as key-value pairs"
  type        = map(string)
  default     = {}
}
variable "secret_arns" {
  description = "Map of env var name to Secrets Manager or SSM Parameter Store ARN"
  type        = map(string)
  default     = {}
}
variable "log_group_name" {
  description = "CloudWatch Logs log group name for container logs"
  type        = string
}
variable "command" {
  description = "Command override for the container entrypoint"
  type        = list(string)
  default     = null
}
variable "entry_point" {
  description = "Entry point for the container"
  type        = list(string)
  default     = null
}
variable "health_check" {
  description = "Container health check configuration"
  type        = object({ command = list(string), interval = optional(number, 30), timeout = optional(number, 5), retries = optional(number, 3), startPeriod = optional(number, 60) })
  default     = null
}
variable "operating_system_family" {
  description = "OS family for Fargate runtime platform (LINUX, WINDOWS_SERVER_2019_FULL, etc.)"
  type        = string
  default     = "LINUX"
}
variable "cpu_architecture" {
  description = "CPU architecture for Fargate runtime platform (X86_64 or ARM64)"
  type        = string
  default     = "X86_64"
  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture must be X86_64 or ARM64."
  }
}
variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
}
variable "region" {
  description = "AWS region for the task definition"
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
data "aws_region" "current" {}
```

### Step 3: Create CloudWatch Logs log group

```hcl
resource "aws_cloudwatch_log_group" "task" {
  name              = var.log_group_name
  retention_in_days = 30
  tags              = var.tags
}
```

### Step 4: Create execution role (ECS agent)

```hcl
resource "aws_iam_role" "execution" {
  name = var.execution_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSTaskExecutionAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
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

### Step 5: Attach execution role policies (image pull and logging)

```hcl
resource "aws_iam_role_policy" "execution_ecr" {
  name = "${var.execution_role_name}-ecr"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRAuthToken"
        Effect = "Allow"
        Action = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "ECRPull"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
        ]
        Resource = "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "execution_logs" {
  name = "${var.execution_role_name}-logs"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.task.arn}:*"
      },
    ]
  })
}
```

### Step 6: Attach secrets access policy (conditional)

```hcl
resource "aws_iam_role_policy" "execution_secrets" {
  count = length(var.secret_arns) > 0 ? 1 : 0
  name  = "${var.execution_role_name}-secrets"
  role  = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "ssm:GetParameters",
        ]
        Resource = values(var.secret_arns)
      },
    ]
  })
}
```

### Step 7: Create task role (application runtime)

```hcl
resource "aws_iam_role" "task" {
  name = var.task_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSTaskAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
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

### Step 8: Create the task definition

```hcl
resource "aws_ecs_task_definition" "this" {
  family                   = var.task_family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = var.operating_system_family
    cpu_architecture        = var.cpu_architecture
  }

  container_definitions = jsonencode([
    merge(
      {
        name      = var.container_name
        image     = var.image_uri
        essential = true

        portMappings = [
          for pm in var.port_mappings : {
            containerPort = pm.containerPort
            protocol      = pm.protocol
          }
        ]

        environment = [
          for k, v in var.environment_variables : {
            name  = k
            value = v
          }
        ]

        secrets = [
          for k, v in var.secret_arns : {
            name      = k
            valueFrom = v
          }
        ]

        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = aws_cloudwatch_log_group.task.name
            "awslogs-region"        = data.aws_region.current.name
            "awslogs-stream-prefix" = var.container_name
          }
        }
      },
      var.command != null ? { command = var.command } : {},
      var.entry_point != null ? { entryPoint = var.entry_point } : {},
      var.health_check != null ? {
        healthCheck = {
          command     = var.health_check.command
          interval    = var.health_check.interval
          timeout     = var.health_check.timeout
          retries     = var.health_check.retries
          startPeriod = var.health_check.startPeriod
        }
      } : {},
    )
  ])

  tags = var.tags
}
```

### Step 9: Define outputs

```hcl
output "task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.this.arn
}

output "execution_role_arn" {
  description = "ARN of the execution role used by the ECS agent"
  value       = aws_iam_role.execution.arn
}

output "task_role_arn" {
  description = "ARN of the task role used by the application container"
  value       = aws_iam_role.task.arn
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
git commit -m "Add ECS Fargate task definition"
gh pr create --title "Provision ECS Fargate task definition" --body "Adds Fargate task definition, execution role, task role, CloudWatch Logs, and optional secrets injection"
```

---

## Examples

### Minimal web server task

```hcl
module "api_task" {
  source              = "./modules/fargate-task"
  task_family         = "api-server"
  container_name      = "api"
  image_uri           = "123456789012.dkr.ecr.us-east-1.amazonaws.com/api:sha-abc123"
  cpu                 = 256
  memory              = 512
  execution_role_name = "api-execution-role"
  task_role_name      = "api-task-role"
  log_group_name      = "/ecs/api-server"
  port_mappings       = [{ containerPort = 8080 }]
  environment         = "dev"
  region              = "us-east-1"
  tags                = { Team = "backend" }
}
```

### Worker with secrets and health check

```hcl
module "worker_task" {
  source              = "./modules/fargate-task"
  task_family         = "worker"
  container_name      = "worker"
  image_uri           = "123456789012.dkr.ecr.us-east-1.amazonaws.com/worker:sha-def456"
  cpu                 = 1024
  memory              = 2048
  execution_role_name = "worker-execution-role"
  task_role_name      = "worker-task-role"
  log_group_name      = "/ecs/worker"
  cpu_architecture    = "ARM64"
  environment         = "prod"
  region              = "us-east-1"
  command             = ["python", "-m", "worker"]
  environment_variables = { LOG_LEVEL = "info", QUEUE_NAME = "work-items" }
  secret_arns = {
    DATABASE_URL = "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db-url-AbCdEf"
    API_KEY      = "arn:aws:ssm:us-east-1:123456789012:parameter/prod/api-key"
  }
  health_check = {
    command     = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
    interval    = 30
    timeout     = 5
    retries     = 3
    startPeriod = 120
  }
  tags = { Team = "platform" }
}
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| Use `awsvpc` network mode | Required for Fargate; provides ENI-per-task networking |
| Separate execution role from task role | Execution role is for ECS agent (image pull, logs); task role is for application code (least-privilege per workload) |
| Execution role scoped to specific log group and ECR repo | No wildcard resource permissions except `ecr:GetAuthorizationToken` which requires `*` |
| Secrets read via Secrets Manager or SSM Parameter Store | No plaintext secrets in `.tf`, `.tfvars`, or container environment; ECS injects at task start |
| Trust only `ecs-tasks.amazonaws.com` | Scoped assume-role with `aws:SourceAccount` condition prevents confused deputy |
| Use immutable image tags (digest or git-sha tags) | Mutable tags like `latest` cause silent drift; pinned tags ensure reproducible deployments |
| No secrets in `.tf` or `.tfvars` | Sensitive values injected from Secrets Manager or SSM at runtime |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean |

---

## Outputs

- ECS Fargate task definition with awsvpc networking and configurable CPU/memory
- Execution IAM role trusted by `ecs-tasks.amazonaws.com` with ECR pull and CloudWatch Logs permissions
- Task IAM role trusted by `ecs-tasks.amazonaws.com` for application-level AWS access
- CloudWatch Logs log group with 30-day retention and awslogs driver configuration
- Optional secret injection from Secrets Manager and SSM Parameter Store with scoped IAM policy
- Configurable runtime platform (OS family and CPU architecture)
- Optional health check, command override, and entry point
- Task definition ARN, execution role ARN, and task role ARN exported
