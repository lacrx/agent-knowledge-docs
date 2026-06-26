---
name: create-nextjs-dockerfile
title: Create Next.js Dockerfile
type: skill
topics:
  - docker
  - containerization
  - nextjs
  - typescript
  - fargate
  - aws
summary: >
  Step-by-step skill for creating a production Dockerfile for a Next.js app
  deployed to AWS Fargate. Covers multi-stage build with standalone output,
  .dockerignore, ECR push, and local verification.
references:
  - skills/create-python-dockerfile.md
  - articles/aws/fargate/deploying-nextjs-apps-to-fargate.md
  - articles/aws/fargate/structuring-nextjs-server-for-fargate.md
last-updated: 2026-06-12
---

# Create Next.js Dockerfile

Production Dockerfile for a Next.js app on AWS Fargate. Follow steps in order.

---

## Prerequisites

- `package.json` and `package-lock.json` at project root
- Next.js app with `output: "standalone"` in `next.config.js`
- `/api/health` route returning 200 OK
- AWS CLI configured with ECR permissions, or Docker Hub account
- Docker installed locally

---

## Steps

### Step 1: Enable standalone output

In `next.config.js` (or `next.config.mjs`):

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
};

module.exports = nextConfig;
```

This makes `next build` produce a self-contained `server.js` in `.next/standalone`
that includes only the dependencies needed at runtime. Image size drops from ~1GB to
~150MB.

### Step 2: Create the Dockerfile (multi-stage)

```dockerfile
# ── Dependencies stage ─────────────────────────────────────────
FROM node:20-slim AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# ── Builder stage ──────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Runtime stage ──────────────────────────────────────────────
FROM node:20-slim

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080 \
    HOSTNAME="0.0.0.0"

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.next/standalone ./
COPY --from=builder --chown=appuser:appuser /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:appuser /app/public ./public

USER appuser

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://localhost:${PORT}/api/health').then(r => { if (!r.ok) process.exit(1) })" || exit 1

CMD ["node", "server.js"]
```

Key decisions:
- Three stages: deps → builder → runtime. Only standalone output reaches final image.
- `node:20-slim` not Alpine — native npm modules (sharp, bcrypt) need glibc.
- `npm ci --ignore-scripts` in deps stage — deterministic installs, skip postinstall in isolated stage.
- `NEXT_TELEMETRY_DISABLED=1` — no telemetry calls from build or runtime.
- `HOSTNAME="0.0.0.0"` — Next.js standalone server binds to this; required for container networking.
- Static files and public dir copied separately — standalone output excludes them.
- Non-root `appuser` — Fargate supports this and limits blast radius.
- HEALTHCHECK uses Node `fetch` — no curl needed in slim image.

### Step 3: Create .dockerignore

```
.git
.gitignore
.env
.env.*
.next
node_modules
tests/
__tests__/
*.md
docker-compose*.yml
.eslintrc*
.prettierrc*
tsconfig.tsbuildinfo
coverage/
.vscode
.idea
cypress/
playwright-report/
```

### Step 4: Single-stage variant (simpler, larger image)

Use when standalone output is not an option or for quick prototyping.

```dockerfile
FROM node:20-slim

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://localhost:${PORT}/api/health').then(r => { if (!r.ok) process.exit(1) })" || exit 1

CMD ["npx", "next", "start", "-p", "8080"]
```

Larger image (~1GB) because full `node_modules` and `.next` build cache are included.
Use the multi-stage standalone build for production.

### Step 5: Build and push to ECR

```bash
# Variables
AWS_ACCOUNT_ID="123456789012"
AWS_REGION="us-east-1"
ECR_REPO="my-nextjs-app"
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

### Step 6: Verify locally

```bash
# Build
docker build -t my-nextjs-app:test .

# Run (map port 8080)
docker run --rm -d -p 8080:8080 --name my-nextjs-test my-nextjs-app:test

# Check health
curl -f http://localhost:8080/api/health

# Check logs
docker logs my-nextjs-test

# Cleanup
docker stop my-nextjs-test
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use `node:20-slim`, not Alpine | Alpine uses musl — native npm modules (sharp, bcrypt) need glibc |
| Enable `output: "standalone"` | Self-contained server.js with only runtime deps; ~150MB vs ~1GB |
| Run as non-root user | Fargate supports non-root; limits blast radius |
| Copy `package.json` before source | Docker layer cache: dep layer survives source-only changes |
| No secrets in image | Use ECS task definition `secrets` from Secrets Manager or SSM Parameter Store |
| Port must match task definition | Default 8080; change Dockerfile and Fargate `containerPort` together |
| Set `HOSTNAME="0.0.0.0"` | Standalone server binds to this; without it, listens on 127.0.0.1 only |

---

## Outputs

- `Dockerfile` — production multi-stage with standalone output (or single-stage variant)
- `.dockerignore` — excludes dev files, node_modules, and secrets from build context
- `next.config.js` updated with `output: "standalone"`
- Container image pushed to ECR or Docker Hub
- Verified locally via health check endpoint
