---
title: AWS Web App Networking
topics:
  - aws
  - networking
  - web-applications
  - infrastructure-as-code
  - terraform
skills:
  - provision-route53-zone
  - provision-fargate-task
  - provision-rds-instance
  - provision-ecr-repository
summary: >
  Networking patterns for AWS web applications — VPC layout, subnet strategy, security groups, load balancers, DNS, TLS, and how compute and data services fit into the network topology.
aliases:
  - aws vpc architecture
  - aws subnet design
  - aws alb networking
related:
  - aws-cloudwatch-logging-monitoring
last-updated: 2026-06-25
---

# AWS Web App Networking

## Overview

Every web application on AWS sits inside a networking layer that determines what can reach it, what it can reach, and how traffic flows between components. Getting the network design right early matters because retrofitting VPC layout, subnet placement, or security group strategy after services are running is disruptive and error-prone.

The core pattern for most web applications is straightforward: a VPC with public and private subnets across multiple availability zones, an Application Load Balancer in the public subnets, compute (Fargate, Lambda, EC2) in private subnets, and data stores (RDS, ElastiCache, DynamoDB endpoints) accessible only from within the VPC. DNS and TLS termination happen at the load balancer or API Gateway edge. This article explains why this pattern works, where to deviate, and what mistakes to avoid.

Most teams should start with this standard layout and only add complexity (transit gateways, PrivateLink, multi-VPC architectures) when they have a concrete requirement for it. Premature network segmentation creates operational overhead without proportional security benefit.

> **Skill:** For Terraform implementation of individual components, use the `provision-fargate-task`, `provision-rds-instance`, `provision-route53-zone`, and `provision-ecr-repository` skills.

---

## VPC and Subnet Layout

A VPC is a logically isolated network within an AWS region. You choose a CIDR block (the IP address range) and carve it into subnets distributed across availability zones (AZs). The fundamental decision is which subnets are public (have a route to an internet gateway) and which are private (route outbound traffic through a NAT gateway or have no internet access at all).

### Standard Two-Tier Layout

| Subnet Type | AZ-a | AZ-b | AZ-c | Purpose |
|---|---|---|---|---|
| **Public** | 10.0.1.0/24 | 10.0.2.0/24 | 10.0.3.0/24 | ALB, NAT gateways, bastion hosts |
| **Private** | 10.0.11.0/24 | 10.0.12.0/24 | 10.0.13.0/24 | Fargate tasks, Lambda, RDS, ElastiCache |

Use at least two AZs for high availability. Three is standard for production. The ALB requires subnets in at least two AZs.

### CIDR Planning

Choose a VPC CIDR that leaves room for growth and does not overlap with other VPCs you may need to peer with. A `/16` (65,536 addresses) is common for production VPCs. Avoid using `10.0.0.0/16` everywhere — if you ever need VPC peering or transit gateway connectivity, overlapping CIDRs will block it.

```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}
```

The `enable_dns_support` and `enable_dns_hostnames` settings are required for Route 53 private hosted zones and for services like RDS that expose DNS endpoints.

---

## Internet and NAT Routing

### Public Subnets

A subnet is "public" because its route table has a route sending `0.0.0.0/0` traffic to an internet gateway (IGW). Resources in public subnets can receive inbound traffic from the internet if they have a public IP or Elastic IP. In practice, the only things that belong in public subnets are:

- Application Load Balancers
- NAT Gateways
- Bastion hosts (if you use them — most teams should use SSM Session Manager instead)

### Private Subnets and NAT

Private subnets route `0.0.0.0/0` through a NAT gateway sitting in a public subnet. This allows outbound internet access (pulling container images, calling external APIs) without accepting inbound connections from the internet.

NAT gateways cost money: roughly $0.045/hour per gateway plus $0.045/GB of data processed. For production, deploy one NAT gateway per AZ for resilience. For dev/staging, a single NAT gateway is acceptable to save cost.

```hcl
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public_a.id
}

resource "aws_route" "private_nat" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main.id
}
```

### VPC Endpoints: Avoiding NAT for AWS Services

If your private subnets only need to reach AWS services (ECR, S3, CloudWatch, Secrets Manager), consider VPC endpoints instead of NAT gateways. Gateway endpoints (S3, DynamoDB) are free. Interface endpoints (most other services) cost about $0.01/hour per AZ but eliminate NAT data processing charges for that traffic.

For Fargate workloads pulling images from ECR, the relevant endpoints are:

- `com.amazonaws.<region>.ecr.api`
- `com.amazonaws.<region>.ecr.dkr`
- `com.amazonaws.<region>.s3` (gateway endpoint — ECR stores layers in S3)
- `com.amazonaws.<region>.logs` (for CloudWatch log delivery)

---

## Security Groups

Security groups are stateful firewalls attached to ENIs (elastic network interfaces). Every resource with a network interface — ALB, Fargate task, RDS instance, Lambda in a VPC — has one or more security groups controlling inbound and outbound traffic.

### Design by Reference, Not by CIDR

The most maintainable pattern is to reference security groups by ID rather than by CIDR block. This creates a chain of trust: the ALB security group allows inbound 443 from the internet, the application security group allows inbound traffic only from the ALB security group, and the database security group allows inbound traffic only from the application security group.

```hcl
# ALB accepts HTTPS from anywhere
resource "aws_security_group" "alb" {
  vpc_id = aws_vpc.main.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# App accepts traffic only from ALB
resource "aws_security_group" "app" {
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
}

# Database accepts traffic only from app
resource "aws_security_group" "db" {
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}
```

This approach means you never have to update CIDR rules when IPs change, and the blast radius of a compromised component is limited to what its security group chain permits.

### Egress Rules

The default security group egress rule allows all outbound traffic. For production, consider restricting egress to known destinations (AWS service endpoints, specific external APIs). This limits the damage if an application is compromised, but adds operational complexity. Most teams leave egress open and rely on other controls (IAM, network ACLs, monitoring) for defense in depth.

---

## Load Balancer Placement and Configuration

### Application Load Balancer (ALB)

The ALB sits in public subnets and distributes traffic to targets (Fargate tasks, EC2 instances, Lambda functions) in private subnets. Key configuration decisions:

| Setting | Recommendation | Rationale |
|---|---|---|
| **Scheme** | `internet-facing` | Required for public web apps; `internal` for service-to-service |
| **Subnets** | Public subnets in 2+ AZs | ALB needs public subnets to receive internet traffic |
| **Idle timeout** | 60s default, tune for your app | WebSocket or long-poll apps may need higher values |
| **Access logs** | Enable to S3 | Essential for debugging and compliance; minimal cost |
| **Deletion protection** | Enable in production | Prevents accidental `terraform destroy` from removing the ALB |

### Target Groups and Health Checks

Target groups define how the ALB routes to your application. For Fargate, use `target_type = "ip"` (Fargate does not support instance-type targets). Set the health check path to a lightweight endpoint that verifies the application is functional without hitting the database on every check.

```hcl
resource "aws_lb_target_group" "app" {
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
```

---

## DNS and TLS Termination

### Route 53

Route 53 manages DNS for your domain. For web applications, the typical setup is:

1. A public hosted zone for your domain (e.g., `example.com`)
2. An alias record pointing your domain (or subdomain) to the ALB
3. ACM (AWS Certificate Manager) providing a TLS certificate validated via DNS

Alias records are AWS-specific DNS records that work like CNAMEs but resolve at the DNS level without an extra hop. They are free (no per-query charge) and work at the zone apex (`example.com`, not just `www.example.com`).

> **Skill:** For setting up Route 53 hosted zones and records with Terraform, use the `provision-route53-zone` skill.

### TLS Termination

Terminate TLS at the ALB. This means the ALB holds the certificate, handles the TLS handshake, and forwards plain HTTP to your application in the private subnet. This is the right choice for most applications because:

- ACM certificates are free and auto-renew when validated via DNS
- The ALB handles cipher suite negotiation and protocol upgrades
- Your application does not need to manage certificates
- Traffic between the ALB and your application stays within the VPC on a private network

```hcl
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.main.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# Redirect HTTP to HTTPS
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
```

Always add an HTTP-to-HTTPS redirect listener. Without it, users hitting port 80 get a connection refused or see an unencrypted page.

---

## Service Placement in the Network

### Where Each Service Lives

| Service | Subnet | Internet Access | Notes |
|---|---|---|---|
| **ALB** | Public | Inbound + outbound | Internet-facing entry point |
| **Fargate tasks** | Private | Outbound via NAT or VPC endpoints | No inbound from internet; ALB routes to them |
| **RDS** | Private | None (ideally) | No internet access needed; use VPC endpoints for backups |
| **ElastiCache** | Private | None | In-VPC only; no public accessibility option |
| **Lambda (VPC-attached)** | Private | Outbound via NAT or VPC endpoints | Only attach to VPC if it needs VPC resources |
| **NAT Gateway** | Public | Outbound | Provides internet access for private subnet resources |
| **Bastion / SSM** | Public or private | Varies | SSM Session Manager eliminates need for bastion hosts |

### Fargate Networking

Fargate tasks in `awsvpc` network mode get their own ENI and private IP address within the subnet. This means each task is a first-class citizen in the VPC — security groups attach directly to the task, and the task appears as a distinct IP to the database and other services.

For Fargate tasks pulling images at startup, ensure either NAT gateway access or ECR VPC endpoints are configured. A common failure mode is deploying a Fargate task to a private subnet with no outbound internet access and no ECR endpoints — the task hangs during image pull and eventually times out.

> **Skill:** For Fargate task definition and service configuration, use the `provision-fargate-task` skill.

### RDS Networking

RDS instances should be in a DB subnet group spanning private subnets across multiple AZs. Never enable the "Publicly Accessible" flag in production. Access should only come from application security groups within the VPC.

The RDS DNS endpoint resolves to a private IP within your VPC. For Multi-AZ deployments, the DNS endpoint automatically fails over to the standby instance — your application does not need to handle IP changes.

> **Skill:** For RDS provisioning including subnet groups and parameter groups, use the `provision-rds-instance` skill.

### Lambda and VPC Attachment

Only attach Lambda functions to a VPC if they need to access VPC resources (RDS, ElastiCache, internal services). VPC-attached Lambda functions use ENIs in your subnets, which adds cold start latency and consumes IP addresses. If your Lambda only calls external APIs or AWS services, keep it outside the VPC.

---

## Multi-Service Communication Patterns

### Service-to-Service Within a VPC

For Fargate services that need to communicate with each other, use AWS Cloud Map (service discovery) or an internal ALB. Cloud Map registers Fargate task IPs in a private DNS namespace, allowing services to find each other by name (e.g., `api.internal`). An internal ALB provides load balancing and health checking between services but adds cost.

### Accessing AWS Services From Private Subnets

Private subnet resources reach AWS services (Secrets Manager, SQS, SNS, S3) via:

1. **NAT gateway** — simplest, works for everything, but costs money per GB
2. **VPC interface endpoints** — per-service, avoids NAT costs, keeps traffic on the AWS backbone
3. **VPC gateway endpoints** — free, but only available for S3 and DynamoDB

For cost-sensitive workloads that transfer significant data to S3, the gateway endpoint alone can save meaningful money versus routing that traffic through NAT.

---

## Infrastructure as Code Considerations

### Terraform Module Structure

Organize networking resources into a dedicated module that other modules reference:

```
modules/
  networking/
    main.tf          # VPC, subnets, route tables
    security.tf      # Security groups
    outputs.tf       # VPC ID, subnet IDs, SG IDs
  compute/
    fargate.tf       # References networking outputs
  data/
    rds.tf           # References networking outputs
```

This separation ensures that networking changes are reviewed independently from application changes, and that subnet IDs and security group IDs are passed as variables rather than hardcoded.

> **Skill:** For scaffolding a Terraform AWS repository with proper module structure, use the `scaffold-terraform-aws-repo` skill.

### State Management

Networking resources are long-lived and shared. Store Terraform state for networking in a separate state file from application resources. This prevents a bad application deployment from accidentally modifying VPC resources and limits the blast radius of `terraform destroy`.

---

## Common Mistakes

### Exposing Databases to the Internet

Setting `publicly_accessible = true` on an RDS instance is the most common and most dangerous networking mistake. Even with strong passwords, a public database endpoint is a target for credential stuffing, brute force, and zero-day exploits. Keep databases in private subnets with security groups that only allow application traffic.

### Over-Broad Security Groups

A security group with `0.0.0.0/0` on port 5432 (PostgreSQL) or port 3306 (MySQL) is effectively no firewall at all. Use security group references instead of CIDR blocks, and limit inbound rules to the specific ports and source groups required.

### Placing Application Containers in Public Subnets

Fargate tasks do not need to be in public subnets. The ALB handles internet-facing traffic and forwards it to tasks in private subnets. Placing tasks in public subnets with public IPs exposes them directly to the internet, bypassing the ALB's security controls and health checking.

### Forgetting NAT or VPC Endpoints for Private Subnets

A Fargate task in a private subnet with no NAT gateway and no VPC endpoints cannot pull its container image, send logs to CloudWatch, or retrieve secrets. The task will hang on startup with no clear error message. Always verify outbound connectivity before deploying to private subnets.

### Using a Single Availability Zone

A single-AZ deployment has no resilience to AZ failures. AWS AZ outages are rare but real. Spread subnets and services across at least two AZs, and ensure the ALB, Fargate service, and RDS Multi-AZ are all configured for cross-AZ operation.

### Ignoring NAT Gateway Costs

NAT gateways charge per hour and per GB processed. For workloads that pull large container images frequently (e.g., on every deployment with many tasks), the data processing charges add up. Use VPC endpoints for ECR and S3 to reduce NAT traffic, and right-size your container images.

---

## Trade-offs

| Decision | Simpler/Cheaper | More Isolated/Resilient |
|---|---|---|
| **NAT gateways** | 1 per VPC (single AZ) | 1 per AZ (survives AZ failure) |
| **VPC endpoints** | Skip them, use NAT for everything | Add endpoints for high-traffic services |
| **Security group egress** | Allow all outbound | Restrict to known destinations |
| **Subnet tiers** | 2 tiers (public + private) | 3 tiers (public + app + data) |
| **VPC count** | Single VPC for all environments | Separate VPCs per environment |
| **DNS** | Use ALB DNS name directly | Custom domain with Route 53 + ACM |

Start simple. A two-tier VPC with one NAT gateway, reference-based security groups, and TLS at the ALB covers the vast majority of web applications. Add complexity only when you have a specific requirement — compliance, multi-team isolation, or traffic volume — that demands it.
