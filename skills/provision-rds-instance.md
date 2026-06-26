---
name: provision-rds-instance
title: Provision RDS Instance
type: skill
topics:
  - terraform
  - aws
  - rds
  - postgresql
  - infrastructure-as-code
summary: >
  Provision an AWS RDS PostgreSQL instance using Terraform with encrypted storage,
  multi-AZ, automated backups, Secrets Manager password, least-privilege security
  group, and deletion protection.
references:
  - skills/scaffold-terraform-aws-repo.md
  - articles/aws/aws-web-app-networking.md
last-updated: 2026-06-15
---

# Provision RDS Instance

Create a production RDS PostgreSQL instance with networking, security, and
backup configuration. Follow steps in order.

---

## Prerequisites

- Terraform >= 1.5
- AWS provider configured (`provider "aws"` block with region)
- VPC with at least 2 private subnets across different AZs
- Terraform state backend configured (see `scaffold-terraform-aws-repo`)

---

## Steps

### Step 1: Define variables

```hcl
variable "instance_identifier" {
  description = "RDS instance identifier"
  type        = string
}

variable "engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "16.3"
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Initial storage in GB"
  type        = number
  default     = 16
}

variable "max_allocated_storage" {
  description = "Max storage for autoscaling in GB"
  type        = number
  default     = 50
}

variable "db_name" {
  description = "Name of the default database to create"
  type        = string
}

variable "master_username" {
  description = "Master username for the RDS instance"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for the DB subnet group (2+ AZs)"
  type        = list(string)
}

variable "vpc_id" {
  description = "VPC ID for the security group"
  type        = string
}

variable "app_cidr_blocks" {
  description = "CIDR blocks allowed to connect on port 5432"
  type        = list(string)
}

variable "multi_az" {
  description = "Enable multi-AZ deployment"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Number of days to retain automated backups"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
```

### Step 2: Generate master password and store in Secrets Manager

```hcl
resource "random_password" "master" {
  length           = 32
  special          = true
  override_special = "!#$%^&*()-_=+"
}

resource "aws_secretsmanager_secret" "rds_password" {
  name = "${var.instance_identifier}-master-password"
  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "rds_password" {
  secret_id     = aws_secretsmanager_secret.rds_password.id
  secret_string = random_password.master.result
}
```

### Step 3: Create DB subnet group

```hcl
resource "aws_db_subnet_group" "this" {
  name       = "${var.instance_identifier}-subnet-group"
  subnet_ids = var.subnet_ids

  tags = var.tags
}
```

### Step 4: Create security group

```hcl
resource "aws_security_group" "rds" {
  name        = "${var.instance_identifier}-rds-sg"
  description = "Allow PostgreSQL access from application subnets"
  vpc_id      = var.vpc_id

  tags = var.tags
}

resource "aws_security_group_rule" "postgres_ingress" {
  type              = "ingress"
  from_port         = 5432
  to_port           = 5432
  protocol          = "tcp"
  cidr_blocks       = var.app_cidr_blocks
  security_group_id = aws_security_group.rds.id
  description       = "PostgreSQL from application subnets"
}

resource "aws_security_group_rule" "egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.rds.id
  description       = "Allow all outbound"
}
```

### Step 5: Create parameter group

```hcl
resource "aws_db_parameter_group" "this" {
  name   = "${var.instance_identifier}-pg-params"
  family = "postgres${split(".", var.engine_version)[0]}"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = var.tags
}
```

### Step 6: Create the RDS instance

```hcl
resource "aws_db_instance" "this" {
  identifier = var.instance_identifier

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.master_username
  password = random_password.master.result

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.this.name
  publicly_accessible    = false

  auto_minor_version_upgrade = true
  backup_retention_period    = var.backup_retention_days
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${var.instance_identifier}-final-snapshot"

  tags = var.tags
}
```

### Step 7: Define outputs

```hcl
output "endpoint" {
  description = "RDS instance endpoint (host:port)"
  value       = aws_db_instance.this.endpoint
}

output "address" {
  description = "RDS instance hostname"
  value       = aws_db_instance.this.address
}

output "port" {
  description = "RDS instance port"
  value       = aws_db_instance.this.port
}

output "arn" {
  description = "RDS instance ARN"
  value       = aws_db_instance.this.arn
}

output "password_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the master password"
  value       = aws_secretsmanager_secret.rds_password.arn
}
```

### Step 8: Format, commit, and PR

```bash
terraform fmt -recursive
git add .
git commit -m "Add RDS PostgreSQL instance"
gh pr create --title "Provision RDS instance" --body "Adds RDS PostgreSQL with subnet group, security group, parameter group, and Secrets Manager password"
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Pin AWS provider version (`~> 5.0`) | Prevents surprise breaking changes |
| No hard-coded passwords | Use `random_password` + Secrets Manager; never put credentials in `.tf` or `.tfvars` |
| Storage encryption mandatory | `storage_encrypted = true` with default KMS key |
| No public accessibility | `publicly_accessible = false`; access only from private subnets |
| Deletion protection on by default | Prevents accidental `terraform destroy` of production data |
| `skip_final_snapshot = false` | Forces a final snapshot before any deletion |
| Least-privilege security group | Ingress locked to `var.app_cidr_blocks` on port 5432 only; no `0.0.0.0/0` |
| Tag all resources with `var.tags` | Consistent cost tracking and resource identification |

---

## Outputs

- RDS PostgreSQL instance with encrypted storage and multi-AZ
- DB subnet group spanning 2+ availability zones
- Security group allowing port 5432 from application CIDRs only
- Parameter group for PostgreSQL tuning
- Master password generated and stored in Secrets Manager
- Endpoint, port, ARN, and password secret ARN exported
