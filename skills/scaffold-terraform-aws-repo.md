---
name: scaffold-terraform-aws-repo
title: Scaffold Terraform AWS Repo
type: skill
topics:
  - terraform
  - aws
  - iac
  - scaffolding
  - project-setup
summary: >
  Scaffold a Terraform IaC repo for managing AWS infrastructure with S3/DynamoDB
  state backend, per-environment config, CI pipeline, and public registry modules.
references:
  - skills/scaffold-python-project.md
  - skills/scaffold-nextjs-project.md
last-updated: 2026-06-13
---

# Scaffold Terraform AWS Repo

Create a complete Terraform repository for AWS infrastructure management.
Follow steps in order.

---

## Prerequisites

- AWS account with SSO configured
- Terraform >= 1.9 installed
- AWS CLI v2 installed
- S3 bucket and DynamoDB table for state backend (create manually or via bootstrap)
- Git installed

---

## Start Here — Companion Skills

After scaffolding the repo, use these skills to add infrastructure:

| Skill | Purpose |
|---|---|
| `provision-s3-bucket` | S3 buckets for storage, static assets, or state |
| `provision-fargate-service` | ECS Fargate services with ALB |
| `provision-fargate-task` | Standalone Fargate task definitions |
| `provision-rds-instance` | RDS PostgreSQL/MySQL instances |
| `provision-lambda-function` | Lambda functions with IAM roles |
| `provision-eventbridge-schedule` | Scheduled event triggers |
| `provision-step-functions` | Step Functions state machines |
| `provision-secrets-manager` | Secrets Manager secrets |
| `provision-ecr-repository` | ECR container image repositories |
| `provision-route53-zone` | Route 53 hosted zones and DNS records |
| `provision-sagemaker-root` | SageMaker domain and studio (if needed) |
| `provision-bedrock-knowledge-base` | Bedrock knowledge base (if needed) |

---

## Steps

### Step 1: Create directory structure

```bash
PROJECT="infra"

mkdir -p ${PROJECT}/environments/{dev,staging,prod}
mkdir -p ${PROJECT}/modules
mkdir -p ${PROJECT}/.github/workflows
```

### Step 2: Create `versions.tf`

```hcl
terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}
```

Backend is configured empty here — values come from `backend.tfvars` per environment.

### Step 3: Create `providers.tf`

```hcl
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.project_name
      ManagedBy   = "terraform"
    }
  }
}
```

### Step 4: Create `variables.tf`

```hcl
variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
}
```

### Step 5: Create `outputs.tf`

```hcl
output "aws_account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region"
  value       = data.aws_region.current.name
}

output "environment" {
  description = "Current environment"
  value       = var.environment
}
```

### Step 6: Create `environments/dev/backend.tfvars`

```hcl
bucket         = "<your-terraform-state-bucket>"
key            = "dev/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "<your-terraform-lock-table>"
encrypt        = true
```

Replace `<your-terraform-state-bucket>` and `<your-terraform-lock-table>` with real values.
Create matching files for `staging/` and `prod/` with different `key` paths.

### Step 7: Create `environments/dev/terraform.tfvars`

```hcl
aws_region   = "us-east-1"
environment  = "dev"
project_name = "my-project"
```

Create matching files for `staging/` and `prod/` with appropriate values.

### Step 8: Create `main.tf` with data sources

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
```

Add resource modules below this as needed. Use companion `provision-*` skills.

### Step 9: Create `.gitignore`

```
# Terraform state
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl

# Crash logs
crash.log
crash.*.log

# Override files
override.tf
override.tf.json
*_override.tf
*_override.tf.json

# CLI config
.terraformrc
terraform.rc

# Secrets (if any tfvars contain sensitive values)
*.auto.tfvars

# IDE
.vscode/
.idea/
*.swp
*~

# OS
.DS_Store
Thumbs.db
```

Note: `backend.tfvars` and `terraform.tfvars` are committed — they contain
configuration, not secrets. Secrets come from AWS Secrets Manager or SSM
Parameter Store at runtime, never from `.tfvars` files.

### Step 10: Local workflow

```bash
# 1. Authenticate via SSO
aws sso login --profile <your-profile>
export AWS_PROFILE=<your-profile>

# 2. Initialize with environment-specific backend
terraform init -backend-config=environments/dev/backend.tfvars

# 3. Plan with environment-specific variables
terraform plan -var-file=environments/dev/terraform.tfvars

# 4. Format check (run before every commit)
terraform fmt -recursive
```

Never run `terraform apply` locally. CI pipeline handles state changes.

### Step 11: Create CI workflow `.github/workflows/terraform.yml`

```yaml
name: Terraform

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read
  pull-requests: write

env:
  TF_VERSION: "1.9"

jobs:
  plan:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: [dev, staging, prod]
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Terraform fmt
        run: terraform fmt -check -recursive

      - name: Terraform init
        run: terraform init -backend-config=environments/${{ matrix.environment }}/backend.tfvars

      - name: Terraform validate
        run: terraform validate

      - name: Terraform plan
        run: terraform plan -var-file=environments/${{ matrix.environment }}/terraform.tfvars -no-color
        continue-on-error: true

  apply:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: [dev]
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Terraform init
        run: terraform init -backend-config=environments/${{ matrix.environment }}/backend.tfvars

      - name: Terraform apply
        run: terraform apply -var-file=environments/${{ matrix.environment }}/terraform.tfvars -auto-approve
```

The `apply` job defaults to `dev` only. Expand the matrix or add manual approval
gates for staging/prod.

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin all module versions (`version = "~> X.0"`) | Prevents surprise breaking changes from upstream modules |
| `terraform fmt -recursive` before every commit | Enforced in CI; keeps diffs clean and reviewable |
| Never run `terraform apply` locally | CI pipeline owns state changes; prevents drift and race conditions |
| No secrets in `.tf` or `.tfvars` files committed to git | Use AWS Secrets Manager or SSM Parameter Store; reference via `data` sources |
| Use variables for environment-specific values | `terraform.tfvars` per environment; no hard-coded strings in `.tf` files |
| Backend config per environment | Separate state files prevent cross-environment contamination |
| Use public registry modules with version pins | `terraform-aws-modules/*` with `~> X.0`; never use unpinned git refs |

---

## Outputs

- Terraform repo with `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `providers.tf`
- Per-environment directories (`dev/`, `staging/`, `prod/`) with `backend.tfvars` and `terraform.tfvars`
- `modules/` directory for local reusable modules
- `.gitignore` covering state files, `.terraform/`, and override files
- GitHub Actions workflow: plan on PR, apply on merge to main
- Default tags (Environment, Project, ManagedBy) on all resources
