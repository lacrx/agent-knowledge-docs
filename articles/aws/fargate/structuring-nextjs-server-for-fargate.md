---
title: Structuring Next.js Server for Fargate
topics:
  - nextjs
  - aws
  - fargate
  - web-applications
  - project-structure
skills:
  - scaffold-nextjs-server
  - create-nextjs-dockerfile
  - configure-prisma-postgres
summary: >
  Architecture patterns for running a Next.js App Router server on AWS Fargate,
  covering component boundaries, standalone output, database access, and common deployment mistakes.
aliases:
  - nextjs fargate architecture
  - next.js ecs deployment structure
  - nextjs server docker patterns
related:
  - deploying-nextjs-apps-to-fargate
  - structuring-fastapi-for-fargate
last-updated: 2026-06-25
---

# Structuring Next.js Server for Fargate

## Overview

Next.js can run as a full server process — not just a static export — making it a candidate for container-based deployment on AWS Fargate. When you use the App Router with server components, server actions, and API routes, you are running a Node.js HTTP server that needs proper containerization, health checks, and environment management to work reliably behind an Application Load Balancer (ALB) in ECS.

This article covers the architecture decisions that matter when targeting Fargate: how to structure your Next.js project so that the production build is container-friendly, how to handle server vs. client component boundaries correctly, how to manage database connections in an ephemeral container environment, and how to avoid the most common deployment mistakes. It does not cover step-by-step procedures — use the companion skills for that.

> **Skill:** For project scaffolding, use the `scaffold-nextjs-server` skill. For Docker configuration, use the `create-nextjs-dockerfile` skill. For database setup, use the `configure-prisma-postgres` skill.

---

## Standalone Output Mode

The single most important `next.config.js` setting for Fargate deployments is `output: "standalone"`. Without it, `next build` produces output that expects the full `node_modules` tree and project source to be present at runtime. The standalone output creates a self-contained directory with only the files needed to run the server.

```js
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
};

module.exports = nextConfig;
```

What standalone mode gives you:

- A `server.js` entry point that starts the HTTP server directly
- A `.next/standalone` directory containing only required dependencies (traced by `@vercel/nft`)
- A dramatically smaller Docker image (often 100-200 MB vs. 1+ GB with full `node_modules`)

You still need to copy `public/` and `.next/static/` into the standalone directory — the build does not include static assets automatically. Your Dockerfile must handle this explicitly.

### What Happens Without Standalone

If you skip `output: "standalone"` and simply run `next start` inside a container, you ship the entire `node_modules` tree. The image bloats, cold start times increase, and you are deploying build-time dependencies (TypeScript, ESLint, testing libraries) into production. This is the most common structural mistake for Next.js on Fargate.

---

## App Router Component Boundaries

The App Router defaults every component to a server component. This is good for Fargate — server components render on the container, reduce client bundle size, and can access backend resources directly. The mistake most teams make is reaching for `"use client"` too early.

### When to Use Server Components

- Data fetching from databases or internal APIs
- Reading environment variables and secrets
- Heavy computation that should not run in the browser
- Components that do not need interactivity or browser APIs

### When to Use Client Components

- Interactive UI: forms, modals, dropdowns, anything with `useState` or `useEffect`
- Browser APIs: `window`, `localStorage`, `IntersectionObserver`
- Third-party client-side libraries (charting, maps, rich text editors)

### The Boundary Rule

Place `"use client"` as deep in the component tree as possible. A common pattern is a server component that fetches data and passes it as props to a small client component that handles interactivity:

```tsx
// app/dashboard/page.tsx — server component (default)
import { db } from "@/lib/db";
import { MetricsChart } from "./metrics-chart";

export default async function DashboardPage() {
  const metrics = await db.metric.findMany({ take: 30 });
  return <MetricsChart data={metrics} />;
}

// app/dashboard/metrics-chart.tsx — client component
"use client";
export function MetricsChart({ data }: { data: Metric[] }) {
  // Interactive chart rendering with client-side library
}
```

Overusing `"use client"` at the page level forces the entire subtree to become client-rendered, negating the benefits of running a server on Fargate in the first place.

---

## API Routes and Server Actions

Next.js provides two mechanisms for server-side logic beyond rendering: API routes (`app/api/*/route.ts`) and server actions.

### API Routes

API routes in the App Router use the web-standard `Request`/`Response` API. They run inside the same Node.js process as your pages. On Fargate, they are served by the same container behind the ALB.

```ts
// app/api/health/route.ts
export async function GET() {
  return Response.json({ status: "ok" }, { status: 200 });
}
```

Use API routes for: webhooks, third-party integrations, endpoints consumed by external services, and health checks.

### Server Actions

Server actions (`"use server"`) allow forms and client components to call server-side functions directly. They are POST requests under the hood, routed through Next.js internals.

Use server actions for: form submissions, mutations triggered by user interaction, and any operation where you want to avoid writing a separate API endpoint.

### When to Prefer Which

| Use Case | Mechanism | Reason |
|---|---|---|
| Health check for ALB | API route | ALB needs a stable HTTP path to poll |
| Form submission | Server action | No separate endpoint boilerplate |
| Webhook receiver | API route | External callers need a stable URL |
| Data mutation from UI | Server action | Integrated with React transitions |
| Public REST API | API route | Standard HTTP semantics expected |

---

## Running Behind ALB and ECS

The Fargate task runs a container that starts `node server.js` (standalone output) listening on a port — typically 3000. The ALB forwards traffic to this port via the ECS target group.

### Health Checks

The ALB target group health check must point to an endpoint that returns 200 quickly. A weak health check is one of the most common causes of container churn in ECS.

Requirements for a good health endpoint:

- Returns 200 with minimal latency (no database queries, no external calls)
- Lives at a predictable path like `/api/health`
- Does not require authentication
- Responds within the health check timeout (default 5 seconds)

A health check that queries the database will cause cascading failures: if the database is slow, containers get marked unhealthy, ECS replaces them, the new containers all hit the slow database simultaneously, and the cycle repeats.

```ts
// app/api/health/route.ts — good: fast, no dependencies
export async function GET() {
  return Response.json({ status: "ok" });
}
```

If you need a deeper health check that verifies database connectivity, put it on a separate path (`/api/health/deep`) and do not use it for the ALB target group. Use it for monitoring or alerting instead.

### Port Configuration

The container port must match what ECS expects. Set it via environment variable:

```dockerfile
ENV PORT=3000
EXPOSE 3000
CMD ["node", "server.js"]
```

Next.js standalone `server.js` respects the `PORT` environment variable by default.

---

## Environment Variables and Secrets

Next.js has a two-tier environment variable system that creates a critical security boundary:

| Prefix | Available Where | Bundled Into Client JS |
|---|---|---|
| `NEXT_PUBLIC_*` | Server and client | Yes — visible in browser |
| No prefix | Server only | No |

### The NEXT_PUBLIC Leak

Any variable prefixed with `NEXT_PUBLIC_` is inlined into the JavaScript bundle at build time. This means it ships to every browser. Never put API keys, database URLs, internal service endpoints, or any secret in a `NEXT_PUBLIC_` variable.

Correct pattern:

```
# .env (or ECS task definition environment)
DATABASE_URL=postgresql://...          # Server only
STRIPE_SECRET_KEY=sk_live_...          # Server only
NEXT_PUBLIC_STRIPE_PUBLIC_KEY=pk_live_... # OK — public key by design
NEXT_PUBLIC_API_BASE_URL=https://api.example.com  # OK — public endpoint
```

### Injecting Secrets on Fargate

Use AWS Secrets Manager or SSM Parameter Store, referenced in the ECS task definition. ECS injects them as environment variables at container start — they never appear in the Docker image or task definition JSON.

```json
{
  "secrets": [
    {
      "name": "DATABASE_URL",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:prod/db-url"
    }
  ]
}
```

Do not bake secrets into the Docker image. Do not pass them as plain-text environment variables in the task definition if they are sensitive.

---

## Database Access with Prisma and Postgres

### Connection Management in Containers

Fargate containers are ephemeral. They start, serve traffic, and may be replaced at any time. Prisma Client creates a connection pool per process. The key concern is managing pool size so you do not exhaust database connections when ECS scales out.

```ts
// lib/db.ts
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    datasources: {
      db: {
        url: process.env.DATABASE_URL,
      },
    },
  });

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = db;
```

The singleton pattern prevents creating multiple `PrismaClient` instances during development hot-reload. In production (standalone mode), there is one process and one client instance.

### Pool Sizing

Prisma's default connection pool limit is 5 (via the `connection_limit` query parameter on the URL). With Fargate autoscaling, if you run 10 tasks with a pool of 5 each, you consume 50 database connections. Size the pool relative to your RDS `max_connections` and expected task count:

```
DATABASE_URL=postgresql://user:pass@host:5432/db?connection_limit=3&pool_timeout=10
```

### Schema Migrations

Do not run `prisma migrate deploy` as part of the container entrypoint. If ECS starts 5 containers simultaneously, they all attempt to migrate concurrently, causing lock contention or failures. Run migrations as a separate ECS task (a one-shot Fargate task) during your CI/CD pipeline before deploying the new service version.

> **Skill:** For full Prisma and Postgres configuration steps, use the `configure-prisma-postgres` skill.

---

## Monolith vs. Split Architecture

A key decision is whether to run one Next.js service that handles both frontend and API, or split into separate frontend and backend services.

### Single Full-Stack Next.js Service

| Advantage | Detail |
|---|---|
| Simpler infrastructure | One ECS service, one ALB target group, one deployment pipeline |
| Co-located data fetching | Server components access the database directly, no network hop |
| Fewer moving parts | No API versioning between frontend and backend |
| Type safety | Shared TypeScript types across the full stack |

| Disadvantage | Detail |
|---|---|
| Scaling is coupled | Cannot scale API and rendering independently |
| Larger blast radius | A backend bug can take down the frontend |
| Mixed concerns | Node.js runtime handles both rendering and business logic |

### Split Frontend + Backend

| Advantage | Detail |
|---|---|
| Independent scaling | Scale API tier separately from rendering tier |
| Technology flexibility | Backend can be Python/FastAPI, Go, or any language |
| Smaller failure domains | Backend outage degrades gracefully if frontend handles errors |

| Disadvantage | Detail |
|---|---|
| Network latency | Frontend-to-backend calls add round trips |
| More infrastructure | Two services, two pipelines, API contracts to maintain |
| Lost server component benefit | Frontend becomes mostly a rendering layer if all data comes from API calls |

**Recommendation:** Start with the monolith. A single Next.js service on Fargate handles most workloads well. Split only when you have a concrete scaling or organizational reason — not preemptively.

---

## Docker Image Structure

The standard multi-stage Dockerfile for Next.js standalone output follows this pattern:

1. **deps stage** — Install production `node_modules` only
2. **builder stage** — Install all dependencies, run `next build`
3. **runner stage** — Copy standalone output, static assets, and public directory into a minimal base image

Key considerations:

- Use `node:20-alpine` or `node:22-alpine` for the runner stage (small image, fast pull)
- Copy `.next/standalone` as the application root
- Copy `.next/static` into `.next/standalone/.next/static`
- Copy `public` into `.next/standalone/public`
- Run as a non-root user
- Set `NODE_ENV=production`

The final image should typically be 150-250 MB. If it is significantly larger, you are likely missing the standalone output or copying unnecessary files.

> **Skill:** For the complete Dockerfile with all stages, use the `create-nextjs-dockerfile` skill.

---

## Common Mistakes

| Mistake | Why It Hurts | Fix |
|---|---|---|
| Missing `output: "standalone"` | Image includes full `node_modules`, bloated and slow | Set `output: "standalone"` in `next.config.js` |
| `NEXT_PUBLIC_` for secrets | API keys, database URLs visible in client JS bundle | Use unprefixed env vars for anything sensitive |
| Health check queries database | Slow DB causes cascading container replacement | Return 200 from a static endpoint with no dependencies |
| `prisma migrate deploy` in entrypoint | Concurrent migrations from multiple tasks cause failures | Run migrations as a separate one-shot Fargate task |
| `"use client"` on page-level components | Entire page renders client-side, wasting the server | Push `"use client"` to the smallest leaf components |
| Hardcoded port in Dockerfile | Conflicts with ECS port mappings | Use `PORT` env var, default to 3000 |
| Forgetting to copy static assets | CSS, images, and fonts 404 in production | Copy `.next/static` and `public/` into standalone dir |
| Running as root in container | Security risk, violates container best practices | Add `USER nextjs` in Dockerfile after creating the user |
| Connection pool too large | Autoscaling exhausts RDS `max_connections` | Set `connection_limit` on DATABASE_URL relative to task count |

---

## References

- [Next.js Standalone Output documentation](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)
- [Next.js Environment Variables](https://nextjs.org/docs/app/building-your-application/configuring/environment-variables)
- [Prisma Connection Management](https://www.prisma.io/docs/orm/prisma-client/setup-and-configuration/databases-connections)
- [AWS ECS Task Definition — Secrets](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html)
