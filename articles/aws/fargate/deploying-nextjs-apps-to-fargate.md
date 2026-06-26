---
title: Deploying Next.js Apps to Fargate
topics:
  - aws
  - fargate
  - nextjs
  - cloud-deployment
  - containerization
skills:
  - create-nextjs-dockerfile
  - scaffold-nextjs-server
  - ecr-push-deploy
summary: >
  Deployment patterns, architecture trade-offs, and operational guidance for running containerized Next.js applications on AWS Fargate.
aliases:
  - nextjs fargate deployment
  - next.js ecs container deploy
  - nextjs docker aws ecs
related:
  - structuring-nextjs-server-for-fargate
  - deploying-python-web-apps-to-fargate
last-updated: 2026-06-25
---

# Deploying Next.js Apps to Fargate

## Overview

Next.js can run as a long-lived Node.js server process behind an Application Load Balancer on AWS Fargate. This deployment model supports server components, server actions, API routes, and streaming — capabilities that static exports or edge deployments cannot fully replicate. Fargate handles the compute infrastructure, so you focus on the container image and the ECS configuration around it.

The deployment pipeline is: build a standalone Next.js image, push to ECR, define an ECS task and service, and route traffic through an ALB. Each step has decisions that affect image size, startup time, security posture, and operational reliability. This article covers those decisions, explains the trade-offs between Fargate and alternative deployment targets, and flags the mistakes that cause the most production incidents.

> **Skill:** For step-by-step procedures, use the `create-nextjs-dockerfile`, `scaffold-nextjs-server`, and `ecr-push-deploy` skills.

---

## Docker Build Flow for Next.js

The standard approach uses a multi-stage Dockerfile with three stages: dependency installation, application build, and production runner.

### Standalone Output Is Non-Negotiable

Set `output: "standalone"` in `next.config.js`. Without it, `next build` produces output that requires the full `node_modules` tree and project source at runtime. Standalone mode uses `@vercel/nft` to trace only the files the server actually imports, producing a self-contained directory with a `server.js` entry point.

```js
// next.config.js
const nextConfig = {
  output: "standalone",
};
module.exports = nextConfig;
```

Standalone output reduces the runtime footprint from 1+ GB (full `node_modules`) to 100-200 MB. It also eliminates build-time dependencies — TypeScript, ESLint, testing libraries — from the production image. Shipping a non-standalone build is the single most common mistake in Next.js containerization.

### Multi-Stage Build Pattern

The three stages serve distinct purposes:

1. **deps** — Install production `node_modules` from the lockfile only. This stage is cached unless `package-lock.json` changes.
2. **builder** — Install all dependencies (including devDependencies), copy source, run `next build`. This stage produces `.next/standalone`, `.next/static`, and `public/`.
3. **runner** — Start from a clean `node:20-alpine` or `node:22-alpine` image. Copy only the standalone output, static assets, and public directory. Run as a non-root user.

Key details the runner stage must handle:

- Copy `.next/standalone` as the application root
- Copy `.next/static` into `.next/standalone/.next/static` (the build does not include static assets in standalone output)
- Copy `public/` into `.next/standalone/public/`
- Set `NODE_ENV=production` and expose the correct port
- Run `node server.js`, not `next start`

If your final image exceeds 300 MB, something is wrong — likely a missing standalone config or unnecessary files copied into the runner stage.

> **Skill:** For the complete multi-stage Dockerfile, use the `create-nextjs-dockerfile` skill.

---

## ECR Push and Image Management

Amazon ECR is the container registry for Fargate deployments. The push flow is straightforward but has operational details that matter.

### Tagging Strategy

Tag every image with an immutable identifier — git SHA, build number, or semver tag. Maintain `:latest` as a convenience alias but never reference it in task definitions. Immutable tags make rollback deterministic: you can point the task definition at a previous SHA and redeploy without ambiguity.

### Lifecycle Policies

Configure ECR lifecycle policies to expire untagged images after a retention window (e.g., 30 days). Without this, your repository accumulates orphaned images that consume storage indefinitely. For most projects, retaining the last 10-20 tagged images is sufficient.

### Image Scanning

Enable ECR image scanning on push. It flags known vulnerabilities in OS packages and Node.js dependencies. Not a substitute for dependency auditing, but a useful last line of defense before deployment.

> **Skill:** For the complete push-and-deploy workflow including authentication, tagging, and service update, use the `ecr-push-deploy` skill.

---

## ECS Task and Service Concepts

### Task Definition

The task definition specifies everything ECS needs to run your container:

| Field | Purpose |
|---|---|
| Container image | ECR URI with tag (e.g., `123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:abc123`) |
| CPU / memory | Fargate enforces fixed combinations (e.g., 256/512, 512/1024, 1024/2048) |
| Port mappings | Container port that receives traffic (typically 3000) |
| Environment / secrets | Runtime configuration injected at launch |
| Log configuration | `awslogs` driver pointing to a CloudWatch log group |
| Task role | IAM role the running container assumes for AWS API calls |
| Execution role | IAM role ECS uses to pull images and write logs |

Each update creates a new task definition revision. Rollback is changing the service to point at a previous revision.

### Service

An ECS service maintains a desired count of running tasks and integrates with the ALB target group. Key settings:

- **desiredCount** — Baseline number of task instances.
- **deploymentConfiguration** — Min/max healthy percent during rolling deploys (e.g., 100/200 means deploy new tasks before draining old ones).
- **healthCheckGracePeriodSeconds** — Time to wait before ALB health checks count. Set this to at least 30-60 seconds for Next.js to allow the Node.js server to start and warm up.

### CPU and Memory Sizing

For Next.js on Fargate, start with these baselines:

| Workload | CPU | Memory | Notes |
|---|---|---|---|
| Lightweight marketing site | 256 | 512 MB | Mostly static pages, few server components |
| Full-stack app with server actions | 512 | 1024 MB | Database queries, server rendering under load |
| Heavy SSR with streaming | 1024 | 2048 MB | Large component trees, concurrent requests |

Monitor CloudWatch metrics for CPU and memory utilization after deployment. If memory utilization regularly exceeds 80%, increase the allocation before you hit OOM kills.

---

## ALB Integration and Health Checks

### Load Balancer Setup

The ALB forwards HTTP/HTTPS traffic to an ECS target group with target type `ip` (required for Fargate's `awsvpc` networking). You need:

- A target group on port 3000 (or whatever `PORT` you configure)
- An HTTPS listener on port 443 with an ACM certificate
- An HTTP listener on port 80 that redirects to HTTPS
- Security groups allowing ALB-to-task traffic on the container port

### Health Checks

The ALB health check is the most operationally significant configuration in the deployment. A poorly designed health check causes cascading container replacement — the most common source of downtime in ECS deployments.

**Good health check:** Returns 200 immediately with no external dependencies.

```ts
// app/api/health/route.ts
export async function GET() {
  return Response.json({ status: "ok" });
}
```

**Bad health check:** Queries the database, calls an external API, or performs expensive computation. If the database is slow, the health check fails, ECS replaces the container, the new container hits the same slow database, and the cycle repeats.

Recommended ALB health check parameters:

| Parameter | Value | Rationale |
|---|---|---|
| Path | `/api/health` | Dedicated endpoint, not `/` (which renders a full page) |
| Interval | 30s | Balance between responsiveness and load |
| Timeout | 5s | Healthy Node.js responds in milliseconds |
| Healthy threshold | 2 | Two passes before receiving traffic |
| Unhealthy threshold | 3 | Three failures before draining |

If you need a deep health check that verifies database connectivity, expose it on a separate path (e.g., `/api/health/deep`) and use it for monitoring dashboards — not the ALB target group.

---

## Server Components, API Routes, and Server Actions on Fargate

Running Next.js as a persistent container process changes the behavior of these features compared to edge or serverless deployments.

### Server Components

Server components render on the container, not in the browser. On Fargate, this means the rendering happens on a long-lived Node.js process with access to the container's environment variables, file system, and network. Server components can query databases directly, access internal services without public endpoints, and perform CPU-intensive rendering without shipping computation to the client.

The key behavioral difference from Vercel's serverless model: on Fargate, the Node.js process persists between requests. Module-level state, in-memory caches, and database connection pools survive across requests. This is an advantage for connection reuse but a footgun for state leaks — mutable module-level variables shared across requests can cause data contamination.

### API Routes

API routes run in the same process. They are standard HTTP handlers — suitable for webhooks, health checks, and endpoints consumed by external clients. On Fargate, they benefit from persistent connection pools and warm process state, making them faster than cold-start serverless equivalents for latency-sensitive operations.

### Server Actions

Server actions are POST requests routed through Next.js internals. On Fargate, they execute on the same container that rendered the originating page. They work reliably in a containerized context, but be aware that during a rolling deployment, a server action initiated on a page served by the old task version may be routed to a new task if the old one has been drained. Ensure server actions are backward-compatible across adjacent deployment versions.

---

## Environment Variables and Secret Handling

### The NEXT_PUBLIC Boundary

Next.js has a two-tier environment variable system with critical security implications:

| Prefix | Available Where | Bundled into Client JS |
|---|---|---|
| `NEXT_PUBLIC_*` | Server and client | Yes — inlined at build time, visible in browser |
| No prefix | Server only | No |

Any variable prefixed with `NEXT_PUBLIC_` is embedded into the JavaScript bundle during `next build`. It ships to every browser. Never put API keys, database URLs, internal service endpoints, or any secret in a `NEXT_PUBLIC_` variable.

Because `NEXT_PUBLIC_` values are inlined at build time, they cannot be changed at runtime. If you need client-accessible configuration that varies per environment, use a server-side API route that returns configuration to the client, or use the Next.js `publicRuntimeConfig` pattern.

### Injecting Secrets with ECS

Use the `secrets` block in the task definition to inject values from AWS Secrets Manager or SSM Parameter Store:

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

ECS resolves these at container launch. The container process sees them as regular environment variables, but they never appear in the Docker image layers or the task definition's plaintext. The execution role must have `secretsmanager:GetSecretValue` permission for the referenced secrets.

Do not bake secrets into the Docker image. Do not pass them as plaintext in the `environment` block if they are sensitive.

---

## Logging

Fargate tasks send container stdout/stderr to CloudWatch Logs via the `awslogs` log driver:

```json
{
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group": "/ecs/nextjs-app",
      "awslogs-region": "us-east-1",
      "awslogs-stream-prefix": "app"
    }
  }
}
```

Next.js logs to stdout by default, which integrates directly. For structured logging that is parseable in CloudWatch Insights, configure a custom logger (pino, winston) to emit JSON. This makes it possible to filter and aggregate logs by request ID, route, status code, or error type.

Avoid using `console.log` for structured data. Template string interpolation produces log lines that are difficult to query. Prefer key-value JSON output.

> **Skill:** For querying and analyzing CloudWatch logs, use the `query-aws-logs` skill.

---

## Scaling

### Auto Scaling Configuration

ECS Service Auto Scaling adjusts `desiredCount` based on CloudWatch metrics. For Next.js applications:

- **CPU utilization > 60-70%** triggers scale-out. Node.js is single-threaded per process, so high CPU means the event loop is saturated.
- **ALB request count per target** is often more responsive than CPU-based scaling for web traffic patterns.
- **Response time P99** via custom metrics can catch degradation before CPU spikes.

Set scale-in cooldown to at least 300 seconds to prevent flapping. Scale-out can be more aggressive (60-120 seconds).

### Fargate Spot

Fargate Spot tasks cost up to 70% less but can be interrupted with two minutes' notice. Use Spot for staging environments, preview deployments, and non-critical background rendering. Do not rely on Spot for production web-serving tasks that require high availability. A mixed capacity provider strategy (e.g., 2 Fargate base + Spot for additional capacity) balances cost and reliability.

---

## Deployment Targets Compared

### Fargate vs. Vercel

| Factor | Fargate | Vercel |
|---|---|---|
| Deployment model | Long-running container | Serverless functions + edge |
| Cold starts | Container pull (30-60s on first deploy, warm after) | Function cold start (100ms-few seconds) |
| Persistent state | Connection pools, in-memory caches survive across requests | No persistent state between invocations |
| Cost at steady traffic | Predictable per-vCPU-hour | Per-invocation, can spike at high traffic |
| Cost at zero traffic | Still paying for running tasks | Near zero |
| Infrastructure control | Full (VPC, security groups, IAM, custom networking) | Limited |
| WebSocket support | Native | Limited (via third-party) |
| Vendor lock-in | AWS (but standard containers) | High (proprietary build system and runtime) |

**Choose Fargate when:** You need persistent connections (database pools, WebSockets), run in a regulated VPC, require predictable costs at steady-state traffic, or need infrastructure-level control.

**Choose Vercel when:** You want zero infrastructure management, traffic is bursty with idle periods, and you do not need persistent server-side state.

### Fargate vs. Lambda@Edge / CloudFront Functions

Lambda@Edge can run Next.js via adapters (OpenNext, SST), but it imposes constraints: 50 MB deployment package limit (zipped), 30-second timeout for origin requests, no persistent connections, and cold start latency. It works well for read-heavy marketing sites but struggles with database-backed applications that need connection pooling.

### Split Frontend/Backend vs. Full-Stack Next.js

Running a single Next.js service on Fargate that handles both rendering and API logic is simpler to operate: one service, one deployment pipeline, shared TypeScript types, co-located data fetching. The trade-off is coupled scaling — you cannot scale rendering independently from API processing.

Split into separate frontend and backend services only when you have a concrete reason: the backend team uses a different language, API and rendering have dramatically different scaling profiles, or you need independent deployment cadences. Do not split preemptively.

---

## Common Mistakes

| Mistake | Impact | Fix |
|---|---|---|
| Missing `output: "standalone"` | 1+ GB image with full `node_modules`, slow deploys | Set `output: "standalone"` in `next.config.js` |
| `NEXT_PUBLIC_` for secrets | API keys, database URLs visible in client JS | Use unprefixed env vars; inject via ECS secrets block |
| Health check queries database | Cascading container replacement when DB is slow | Dedicated `/api/health` endpoint returning 200 with no dependencies |
| No health check grace period | Tasks killed during Node.js startup | Set `healthCheckGracePeriodSeconds` >= 30 on the ECS service |
| Running `next start` instead of `node server.js` | Ignores standalone output, requires full project tree | Use `node server.js` in the CMD directive |
| Forgetting to copy static assets | CSS, images, fonts return 404 in production | Copy `.next/static` and `public/` into standalone directory |
| Running as root in container | Security risk, fails compliance scans | Create non-root user in Dockerfile, use `USER nextjs` |
| Oversized image (500+ MB) | Slow ECR pulls, slow rolling deploys | Multi-stage build with alpine runner, standalone output |
| Mutable module-level state | Data leaks between requests on persistent process | Use request-scoped state; avoid module-level variables that accumulate data |
| No ECR lifecycle policy | Unbounded storage cost from orphaned images | Set expiration for untagged images (e.g., 30 days) |

---

## References

- [Next.js Standalone Output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)
- [Next.js Environment Variables](https://nextjs.org/docs/app/building-your-application/configuring/environment-variables)
- [AWS ECS Task Definition — Secrets](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html)
- [AWS Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
