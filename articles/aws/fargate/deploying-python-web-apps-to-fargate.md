---
title: Deploying Python Web Apps to Fargate
topics:
  - aws
  - fargate
  - python
  - cloud-deployment
  - containerization
skills:
  - create-python-dockerfile
  - provision-fargate-task
  - ecr-push-deploy
summary: >
  Deployment patterns, architecture decisions, and common pitfalls for running containerized Python web apps on AWS Fargate.
aliases:
  - python fargate deployment
  - ecs fargate python
  - python container aws
related:
  - structuring-fastapi-for-fargate
  - deploying-nextjs-apps-to-fargate
last-updated: 2026-06-25
---

# Deploying Python Web Apps to Fargate

## Overview

AWS Fargate is a serverless compute engine for containers that removes the need to manage EC2 instances. You define a container image, specify CPU and memory, and Fargate runs it in an isolated environment. For Python web apps — whether FastAPI, Flask, Django, or a custom ASGI server — Fargate provides a middle ground between Lambda's event-driven model and full EC2 cluster management.

The deployment pipeline follows a consistent pattern: build a container image, push it to Amazon ECR, define an ECS task definition referencing that image, and run the task behind a service with an Application Load Balancer. Each stage has decisions that affect cost, reliability, and developer experience. This article covers those decisions and the reasoning behind them.

> **Skill:** For step-by-step implementation, use the `create-python-dockerfile`, `provision-fargate-task`, and `ecr-push-deploy` skills.

---

## Container Packaging for Python

### Base Image Selection

The base image choice directly affects build time, image size, and security surface area:

| Base Image | Size | Use Case |
|---|---|---|
| `python:3.12-slim` | ~150 MB | General purpose, good default |
| `python:3.12-alpine` | ~50 MB | Smallest size, but musl libc breaks some C-extension packages |
| `python:3.12` | ~900 MB | Full Debian, only when you need system-level build tools at runtime |

Prefer `slim` unless you have a specific reason to deviate. Alpine images cause silent failures with packages that depend on glibc (numpy, pandas, psycopg2). If you need alpine-level size, use a multi-stage build with `slim` as the runtime stage.

### Multi-Stage Builds

Separate build dependencies from the runtime image. Install compilers and headers in the build stage, then copy only the installed packages and application code into a clean runtime stage:

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
COPY --from=builder /install /usr/local
COPY . /app
WORKDIR /app
```

This keeps the final image small and free of build toolchains that expand your attack surface.

### ENTRYPOINT and CMD

Define the process that Fargate will manage. For Python web apps, this is typically a WSGI/ASGI server:

```dockerfile
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Always bind to `0.0.0.0`, not `127.0.0.1`. Fargate routes traffic to the container's network interface — binding to localhost makes the app unreachable from outside the container.

> **Skill:** For the full Dockerfile template with health check and non-root user, use the `create-python-dockerfile` skill.

---

## ECR Image Flow

Amazon Elastic Container Registry (ECR) is the standard registry for Fargate deployments. The flow is:

1. **Create an ECR repository** — one per service, with image scanning and lifecycle policies configured.
2. **Authenticate Docker** — `aws ecr get-login-password | docker login`.
3. **Build and tag** — tag with both a unique identifier (git SHA or build number) and `latest`.
4. **Push** — `docker push` the tagged image.
5. **Update ECS** — point the task definition at the new image tag.

### Tagging Strategy

Never deploy with only `:latest`. Use immutable tags (git SHA, semver, or build ID) so you can roll back to a specific version. Keep `:latest` as a convenience alias for the most recent stable build, but always reference the specific tag in task definitions.

### Lifecycle Policies

Configure ECR lifecycle policies to expire untagged images after a set number of days. Without this, your registry accumulates hundreds of orphaned images, each consuming storage costs.

> **Skill:** For the complete push-and-deploy workflow, use the `ecr-push-deploy` skill.

---

## ECS Task and Service Concepts

### Task Definition

A task definition is a blueprint that specifies:

- **Container image** — the ECR URI with tag
- **CPU and memory** — Fargate enforces specific combinations (e.g., 256 CPU / 512 MB, 512 CPU / 1024 MB)
- **Port mappings** — which container port receives traffic
- **Environment variables and secrets** — runtime configuration
- **Log configuration** — where stdout/stderr goes
- **IAM task role** — what AWS services the running container can access
- **IAM execution role** — what ECS itself needs to pull images and write logs

The task definition is versioned. Each update creates a new revision, which makes rollback straightforward.

### Service

An ECS service maintains a desired count of running tasks and integrates with load balancers. Key settings:

| Setting | Purpose |
|---|---|
| `desiredCount` | Number of task instances to keep running |
| `deploymentConfiguration` | Min/max healthy percent during rolling deploys |
| `healthCheckGracePeriod` | Seconds to wait before ALB health checks count |
| `capacityProviderStrategy` | Fargate vs. Fargate Spot allocation |

### CPU and Memory Sizing

Fargate enforces fixed CPU/memory combinations. For Python web apps:

- **FastAPI / Flask API**: Start with 256 CPU / 512 MB. Increase if you see OOM kills.
- **Django with ORM**: 512 CPU / 1024 MB minimum. Django's memory footprint is higher at baseline.
- **Data-heavy workloads**: 1024 CPU / 2048 MB or higher. Python's GIL means CPU-bound tasks benefit more from multiple task replicas than from larger CPU allocation on a single task.

---

## ALB Integration and Health Checks

### Load Balancer Setup

An Application Load Balancer sits in front of your ECS service. The ALB forwards HTTP/HTTPS traffic to the target group, which routes to healthy task instances. You need:

- A target group with target type `ip` (required for Fargate's `awsvpc` networking)
- A listener rule matching your domain or path pattern
- Security groups allowing ALB-to-task traffic on the container port

### Health Check Configuration

The ALB health check determines whether a task receives traffic. A weak health check is one of the most common causes of deployment failures.

```python
# Dedicated health endpoint — not just "return 200"
@app.get("/health")
async def health():
    # Check that critical dependencies are reachable
    try:
        await db.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception:
        raise HTTPException(status_code=503, detail="database unreachable")
```

Configure the ALB health check to hit this endpoint:

| Parameter | Recommended Value | Rationale |
|---|---|---|
| Path | `/health` | Dedicated endpoint, not `/` |
| Interval | 30s | Frequent enough to catch failures quickly |
| Timeout | 5s | If health check takes longer, something is wrong |
| Healthy threshold | 2 | Two consecutive passes before routing traffic |
| Unhealthy threshold | 3 | Three consecutive failures before draining |

Set `healthCheckGracePeriodSeconds` on the ECS service to at least 60 seconds. Without this, the ALB marks tasks as unhealthy before they finish starting, causing an infinite restart loop.

---

## Runtime Configuration

### Environment Variables

Pass non-sensitive configuration through the task definition's `environment` block:

```json
{
  "environment": [
    {"name": "APP_ENV", "value": "production"},
    {"name": "LOG_LEVEL", "value": "INFO"},
    {"name": "WORKERS", "value": "2"}
  ]
}
```

### Secret Injection

Never bake secrets into the container image. Use the `secrets` block to inject values from AWS Secrets Manager or SSM Parameter Store at task startup:

```json
{
  "secrets": [
    {
      "name": "DATABASE_URL",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db-url"
    }
  ]
}
```

ECS resolves these at launch time. The container process sees them as regular environment variables, but they never appear in the task definition's plaintext or in the image layers.

> **Skill:** For creating and managing secrets, use the `provision-secrets-manager` skill.

### Worker Count

For ASGI servers (uvicorn, hypercorn), set the worker count based on the Fargate CPU allocation. A common formula: `workers = (CPU units / 256) + 1`. For a 512 CPU task, that means 3 workers. Avoid over-provisioning — Python workers are memory-hungry, and exceeding the memory limit triggers an OOM kill with no useful error message.

---

## Logging

Fargate tasks send container stdout/stderr to CloudWatch Logs by default using the `awslogs` log driver:

```json
{
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group": "/ecs/my-python-app",
      "awslogs-region": "us-east-1",
      "awslogs-stream-prefix": "app"
    }
  }
}
```

Use structured JSON logging in your Python app so logs are parseable in CloudWatch Insights:

```python
import structlog
structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
    wrapper_class=structlog.stdlib.BoundLogger,
)
```

Avoid printing to stderr for non-error output. CloudWatch does not distinguish stdout from stderr by default, and mixed streams make filtering difficult.

> **Skill:** For querying and analyzing CloudWatch logs, use the `query-aws-logs` skill.

---

## Scaling

### Auto Scaling

ECS Service Auto Scaling adjusts `desiredCount` based on CloudWatch metrics. Common scaling triggers for Python web apps:

- **CPU utilization > 70%** — scale out. Python's GIL means high CPU usually indicates you need more task replicas.
- **ALB request count per target** — scale based on traffic, not resource usage. Often more responsive.
- **Custom metrics** — queue depth, response latency percentiles.

Set a scale-in cooldown of at least 300 seconds to prevent flapping. Scale-out can be more aggressive (60-120 seconds).

### Fargate Spot

Fargate Spot tasks cost up to 70% less but can be interrupted with two minutes' notice. Use Spot for:

- Non-critical background workers
- Workloads that can tolerate brief interruptions
- Development and staging environments

Do not use Spot for your only production web-serving tasks. A capacity provider strategy mixing Fargate and Fargate Spot (e.g., base of 2 Fargate, additional capacity on Spot) balances cost and reliability.

---

## Networking

Fargate tasks use `awsvpc` networking mode, meaning each task gets its own elastic network interface (ENI) and private IP address. Key decisions:

- **Private subnets with NAT Gateway** — standard for production. Tasks are not directly reachable from the internet; outbound traffic goes through NAT.
- **Public subnets with public IP** — simpler but exposes tasks directly. Only appropriate for development.
- **Security groups** — the task's security group should allow inbound only from the ALB's security group, on the container port.

Fargate tasks in private subnets need a NAT Gateway (or VPC endpoints) to pull images from ECR and send logs to CloudWatch. Forgetting this causes tasks to hang at "PROVISIONING" indefinitely with no clear error.

---

## Fargate vs. Lambda vs. EC2: When to Use What

| Factor | Fargate | Lambda | EC2 (ECS) |
|---|---|---|---|
| Startup time | 30-60s (cold) | 100ms-10s | Depends on instance |
| Max duration | Unlimited | 15 min | Unlimited |
| Persistent connections | Yes (WebSockets, DB pools) | No | Yes |
| Pricing model | Per vCPU-hour + GB-hour | Per invocation + GB-second | Per instance-hour |
| Scaling speed | Minutes | Seconds | Minutes |
| Operational overhead | Low | Lowest | High |
| Max memory | 30 GB | 10 GB | Instance-dependent |

**Choose Fargate when:**
- Your app needs persistent connections (database connection pools, WebSockets)
- Request processing regularly exceeds 30 seconds
- You need consistent, predictable performance without cold starts
- You are running a traditional web framework (Django, Flask, FastAPI with middleware)

**Choose Lambda when:**
- Traffic is bursty with long idle periods (cost drops to zero when idle)
- Each request is stateless and completes in under 15 minutes
- You want the fastest possible scaling response

**Choose EC2-backed ECS when:**
- You need GPU access or specialized instance types
- You need to control the host OS or kernel parameters
- Cost optimization at high, steady-state traffic volumes justifies the operational burden

---

## Common Mistakes

| Mistake | Impact | Fix |
|---|---|---|
| Binding to `127.0.0.1` | Container unreachable from ALB | Bind to `0.0.0.0` |
| No health check grace period | Tasks killed during startup | Set `healthCheckGracePeriodSeconds` >= 60 |
| Secrets baked into image | Credentials visible in ECR image layers | Use `secrets` block with Secrets Manager |
| Oversized images (1 GB+) | Slow deploys, high ECR costs | Multi-stage builds, use `slim` base |
| Running as root | Security violation, fails compliance scans | Add `USER nonroot` in Dockerfile |
| No lifecycle policy on ECR | Unbounded storage cost growth | Set expiration for untagged images |
| Too many uvicorn workers | OOM kills with no useful error | Match workers to Fargate memory allocation |
| Missing NAT Gateway in private subnet | Tasks hang at PROVISIONING | Add NAT Gateway or VPC endpoints |
| Health check on `/` | Returns HTML, not health status | Dedicated `/health` endpoint with dependency checks |
| No structured logging | Logs unparseable in CloudWatch Insights | Use JSON logger (structlog, python-json-logger) |

---

## Related Articles

- **[structuring-fastapi-for-fargate](structuring-fastapi-for-fargate.md)** — How to structure a FastAPI project for Fargate deployment, including middleware, startup/shutdown hooks, and configuration patterns.
- **[deploying-nextjs-apps-to-fargate](deploying-nextjs-apps-to-fargate.md)** — Equivalent deployment guide for Next.js applications on Fargate.
