---
name: create-python-dockerfile
title: Create Python Dockerfile
type: skill
topics:
  - docker
  - containerization
  - python
  - fargate
  - aws
summary: >
  Step-by-step skill for creating a production Dockerfile for a Python FastAPI/uvicorn
  web app deployed to AWS Fargate. Covers single-stage and multi-stage builds, .dockerignore,
  ECR push, and local verification.
references:
  - articles/agent-workflow/anthropic-sdk-fastapi-tools.md
  - skills/scaffold-fastapi.md
  - articles/aws/fargate/deploying-python-web-apps-to-fargate.md
  - articles/aws/fargate/structuring-fastapi-for-fargate.md
  - articles/aws/python-project-scaffolding-aws.md
last-updated: 2026-06-12
---

# Create Python Dockerfile

Production Dockerfile for a Python FastAPI app on AWS Fargate. Follow steps in order.

---

## Prerequisites

- `requirements.txt` at project root with all production dependencies
- App entry point at `src/api/app.py` exposing a FastAPI `app` instance
- `/health` endpoint returning 200 OK
- AWS CLI configured with ECR permissions, or Docker Hub account
- Docker installed locally

---

## Steps

### Step 1: Create the Dockerfile (single-stage)

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

Key decisions:
- `PYTHONDONTWRITEBYTECODE=1` — skip .pyc files, no benefit in containers
- `PYTHONUNBUFFERED=1` — logs flush immediately to CloudWatch
- `requirements.txt` copied before source — Docker layer cache survives source changes
- Non-root `appuser` — Fargate supports this and it limits blast radius
- HEALTHCHECK uses stdlib `urllib` — no curl/wget needed in slim image
- Single worker — Fargate scales horizontally via task count, not worker count

### Step 2: Create .dockerignore

```
.git
.gitignore
.env
.env.*
*.pyc
__pycache__
tests/
docs/
*.md
docker-compose*.yml
requirements-dev.txt
.pytest_cache
.mypy_cache
.ruff_cache
.vscode
.idea
```

### Step 3: Multi-stage build variant (optional)

Use when dependencies include compiled C extensions (e.g., `uvloop`, `cryptography`,
`numpy`) or when minimizing final image size matters.

```dockerfile
# ── Builder stage ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY --from=builder /install /usr/local

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY src/ src/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

Builder stage installs gcc and build headers, compiles wheels, then only the installed
packages carry over to the runtime stage. gcc and headers stay behind.

### Step 4: Build and push to ECR

```bash
# Variables
AWS_ACCOUNT_ID="123456789012"
AWS_REGION="us-east-1"
ECR_REPO="my-app"
IMAGE_TAG="latest"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${REGISTRY}

# Build
docker build -t ${ECR_REPO}:${IMAGE_TAG} .

# Tag for ECR
docker tag ${ECR_REPO}:${IMAGE_TAG} ${REGISTRY}/${ECR_REPO}:${IMAGE_TAG}

# Push
docker push ${REGISTRY}/${ECR_REPO}:${IMAGE_TAG}
```

For Docker Hub instead:

```bash
docker login
docker tag ${ECR_REPO}:${IMAGE_TAG} dockerhubuser/${ECR_REPO}:${IMAGE_TAG}
docker push dockerhubuser/${ECR_REPO}:${IMAGE_TAG}
```

### Step 5: Verify locally

```bash
# Build
docker build -t my-app:test .

# Run (map port 8080)
docker run --rm -d -p 8080:8080 --name my-app-test my-app:test

# Check health
curl -f http://localhost:8080/health

# Check logs
docker logs my-app-test

# Cleanup
docker stop my-app-test
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use `python:3.12-slim`, not Alpine | Alpine uses musl libc — many Python wheels are glibc-only and require recompilation, increasing build time and image size |
| Run as non-root user | Fargate supports non-root containers; limits damage from container escape |
| Copy `requirements.txt` before source | Docker layer cache: dependency layer survives source-only changes, cutting rebuild time |
| No secrets in image | Use ECS task definition `secrets` block to inject from AWS Secrets Manager or SSM Parameter Store at runtime |
| Port must match task definition | Default 8080; change both the Dockerfile `EXPOSE`/`CMD` and the Fargate task definition `containerPort` together |

---

## Outputs

- `Dockerfile` — production-ready, single-stage (or multi-stage variant)
- `.dockerignore` — excludes dev files and secrets from build context
- Container image pushed to ECR or Docker Hub
- Verified locally via health check endpoint
