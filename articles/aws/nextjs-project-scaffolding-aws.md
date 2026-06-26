---
title: Next.js Project Scaffolding for AWS
topics:
  - project-structure
  - nextjs
  - aws
  - scaffolding
  - web-applications
skills:
  - scaffold-nextjs-project
  - scaffold-nextjs-server
  - configure-prisma-postgres
summary: >
  Standard project structure, component boundaries, and AWS deployment considerations for Next.js applications targeting Fargate.
aliases:
  - nextjs aws project structure
  - next.js scaffolding aws
  - nextjs fargate project layout
related:
  - python-project-scaffolding-aws
last-updated: 2026-06-25
---

# Next.js Project Scaffolding for AWS

## Overview

Next.js applications targeting AWS deployment need deliberate structural choices that vanilla tutorials skip. The App Router introduced server components, server actions, and route handlers that blur the line between frontend and backend. When you deploy to Fargate behind a load balancer, those boundaries matter for security, performance, and operational clarity.

This article covers how to organize a Next.js project for AWS, where to draw the server/client boundary, how to handle environment variables safely, and when to split into separate services versus keeping a monolithic full-stack app. It complements the companion skills that handle the actual scaffolding and configuration steps.

> **Skill:** For step-by-step project creation, use the `scaffold-nextjs-project` skill. For server-side configuration, use `scaffold-nextjs-server`. For database setup, use `configure-prisma-postgres`.

---

## App Router Project Layout

A well-organized Next.js project for AWS follows a structure that separates concerns and makes the server/client boundary explicit:

```
src/
  app/
    layout.tsx              # Root layout (server component)
    page.tsx                # Landing page
    (auth)/
      login/page.tsx        # Grouped route for auth flows
      register/page.tsx
    dashboard/
      layout.tsx            # Nested layout with auth check
      page.tsx
    api/
      health/route.ts       # Health check for ALB
      webhooks/
        stripe/route.ts     # Webhook handlers
  components/
    ui/                     # Shared presentational components
    forms/                  # Client components with interactivity
    layouts/                # Layout-level server components
  lib/
    db.ts                   # Prisma client singleton
    auth.ts                 # Auth utilities
    aws/                    # AWS SDK wrappers (S3, SES, etc.)
    actions/                # Server actions grouped by domain
  types/                    # Shared TypeScript types
  middleware.ts             # Edge middleware for auth/redirects
prisma/
  schema.prisma
  migrations/
tests/
  unit/
  integration/
  e2e/
docker/
  Dockerfile
  .dockerignore
terraform/                  # Infrastructure as code (separate repo preferred)
```

### Key layout decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| `src/` directory | Use it | Keeps config files at root, application code contained |
| Route groups `(name)` | Use for logical grouping | Prevents URL pollution while organizing related routes |
| `lib/` vs `utils/` | Prefer `lib/` | Signals internal modules, not random helpers |
| `components/` split | `ui/` + domain folders | Prevents a flat directory with 200 files |
| `api/` routes | Minimal, webhook/health only | Prefer server actions over API routes for app-internal calls |

---

## Server vs Client Component Boundaries

The App Router defaults all components to server components. This is the correct default for AWS-deployed apps because server components run on the container, never ship JavaScript to the browser, and can access secrets directly.

### When to use server components

- Data fetching from databases or AWS services
- Rendering that depends on secrets or internal APIs
- Layout and page-level components
- Any component that does not need browser interactivity

### When to use client components

- Form inputs, modals, dropdowns, and interactive UI
- Components using `useState`, `useEffect`, or browser APIs
- Third-party libraries that require the DOM (charts, maps, editors)

### The boundary pattern

Place the `"use client"` directive as deep in the tree as possible. A common mistake is marking an entire page as a client component because one button needs `onClick`. Instead, extract only the interactive piece:

```tsx
// src/app/dashboard/page.tsx — server component (default)
import { getMetrics } from "@/lib/actions/metrics";
import { MetricsChart } from "@/components/dashboard/metrics-chart";

export default async function DashboardPage() {
  const metrics = await getMetrics();  // runs on server, can use secrets
  return (
    <div>
      <h1>Dashboard</h1>
      <MetricsChart data={metrics} />  {/* client component for interactivity */}
    </div>
  );
}
```

```tsx
// src/components/dashboard/metrics-chart.tsx
"use client";
export function MetricsChart({ data }: { data: Metric[] }) {
  // Chart library, useState, etc.
}
```

This pattern keeps data fetching on the server and only ships the interactive chart code to the browser.

---

## Server Actions and API Routes

### Server actions for internal operations

Server actions replace most API routes for operations triggered by the application itself. They run on the server, are type-safe, and integrate with form handling:

```tsx
// src/lib/actions/projects.ts
"use server";

import { db } from "@/lib/db";
import { revalidatePath } from "next/cache";

export async function createProject(formData: FormData) {
  const name = formData.get("name") as string;
  await db.project.create({ data: { name } });
  revalidatePath("/dashboard");
}
```

### API routes for external consumers

Use `route.ts` files only when external systems need an HTTP endpoint:

- **Health checks**: ALB needs `GET /api/health` returning 200
- **Webhooks**: Stripe, GitHub, or other services posting to your app
- **Public APIs**: If your app exposes an API to third parties

Do not create API routes that are only called by your own frontend. Server actions are simpler and avoid the serialization overhead.

---

## Configuration and Environment Variables

### The NEXT_PUBLIC prefix rule

Next.js exposes variables prefixed with `NEXT_PUBLIC_` to browser JavaScript at build time. This is a hard boundary:

| Prefix | Available on server | Available in browser | Embedded at |
|--------|-------------------|---------------------|-------------|
| `NEXT_PUBLIC_` | Yes | Yes | Build time |
| No prefix | Yes | No | Runtime |

### What goes where

```bash
# .env.local (not committed, development only)
DATABASE_URL=postgresql://localhost:5432/myapp
AWS_REGION=us-east-1
STRIPE_SECRET_KEY=sk_test_...

# These are safe to expose — they contain no secrets
NEXT_PUBLIC_APP_URL=https://myapp.example.com
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

On AWS, inject non-public variables through ECS task definition environment or AWS Secrets Manager. Never bake secrets into the Docker image.

### Runtime configuration for Fargate

Since `NEXT_PUBLIC_` variables are inlined at build time, you need a strategy for values that differ per environment. Two approaches:

1. **Build per environment** — Build separate images for staging and production. Simple but slow.
2. **Runtime injection** — Use a `__ENV.js` script loaded by the root layout that reads from a server endpoint at page load. More complex but allows a single image across environments.

For most teams, building per environment is the right starting point. Optimize to runtime injection only if build times become a bottleneck.

---

## Prisma Placement and Database Access

Prisma lives at the project root (not inside `src/`) because the CLI expects `prisma/schema.prisma` at the project root by default.

### Client singleton

Create a single Prisma client instance to avoid exhausting database connections during development hot reloads:

```ts
// src/lib/db.ts
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const db = globalForPrisma.prisma || new PrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = db;
}
```

### Migrations in deployment

Run `prisma migrate deploy` as a separate ECS task or as part of a CI/CD step before the new container starts serving traffic. Do not run migrations inside the application startup script — a failed migration should not take down your running service.

> **Skill:** For complete Prisma setup including schema design and migration workflow, use the `configure-prisma-postgres` skill.

---

## Docker and Standalone Output for Fargate

Next.js provides a `standalone` output mode that produces a minimal Node.js server without the full `node_modules` tree. This is essential for Fargate deployments where image size affects pull time and cold start.

```js
// next.config.js
module.exports = {
  output: "standalone",
};
```

The standalone build produces a `server.js` file and a minimal `.next/standalone` directory. Your Dockerfile copies only what is needed:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx prisma generate
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
```

Key points for Fargate:

- Use multi-stage builds to keep the final image small (typically under 200MB)
- The health check endpoint (`/api/health`) must respond within the ALB's timeout
- Set `HOSTNAME=0.0.0.0` so the server binds to all interfaces inside the container
- Copy `prisma/` into the runtime stage only if you run migrations from the container

> **Skill:** For the full Dockerfile with all production optimizations, use the `create-nextjs-dockerfile` skill.

---

## Monolith vs Split Services

### When to keep a single Next.js app

- Early-stage projects where speed of iteration matters most
- Small teams (1-4 developers) where operational overhead of multiple services is not justified
- Applications where the frontend and backend share types and change together
- Projects where server components and server actions cover all backend needs

### When to split frontend and backend

- The backend serves multiple clients (web app, mobile app, third-party integrations)
- Backend processing has different scaling characteristics (CPU-heavy ML, long-running jobs)
- Teams are large enough to own services independently
- The backend is in a different language (Python/FastAPI for ML workloads)

### The hybrid approach

A practical middle ground: keep Next.js as the full-stack app for user-facing features, but extract specific backend capabilities into separate Fargate services when they have different scaling or deployment needs. The Next.js app calls these services through server actions or server components, keeping the API internal.

> **Skill:** For structuring a split server configuration, use the `scaffold-nextjs-server` skill.

---

## Testing Structure

Organize tests to mirror the source structure and separate by speed:

```
tests/
  unit/                    # Fast, no network, no database
    components/
    lib/
  integration/             # Database, external services (mocked or local)
    actions/
    api/
  e2e/                     # Full browser tests (Playwright)
    dashboard.spec.ts
    auth.spec.ts
```

- **Unit tests** run against server actions, utility functions, and component rendering (without a browser). Use Vitest or Jest.
- **Integration tests** run against API routes and server actions with a test database. Use Vitest with Prisma pointed at a test database.
- **E2E tests** run the full application in a browser. Use Playwright.

Keep test configuration in `vitest.config.ts` at the project root. For Playwright, use `playwright.config.ts`.

> **Skill:** For setting up the test harness with all configuration files, use the `setup-nextjs-tests` skill.

---

## Common Mistakes

| Mistake | Why it happens | What to do instead |
|---------|---------------|-------------------|
| Marking pages as `"use client"` | Developer wants `onClick` on one element | Extract only the interactive component as a client component |
| Putting business logic in `page.tsx` | Seems convenient for small apps | Move logic to `lib/actions/` or `lib/` modules for testability and reuse |
| Using `NEXT_PUBLIC_` for secrets | Misunderstanding the prefix convention | Any `NEXT_PUBLIC_` value is visible in browser source; use unprefixed vars and server-only access |
| Skipping the health check endpoint | Not thinking about ALB requirements | ALB needs a reliable health endpoint; `/api/health` returning `{ status: "ok" }` is the minimum |
| Running `prisma migrate` at container start | Simpler than a separate migration step | A failed migration crashes all containers; run migrations as a one-off ECS task in CI/CD |
| Not using `standalone` output | Default Next.js output works locally | Without standalone, the Docker image includes all of `node_modules` — 1GB+ images with slow pulls |
| Importing server-only code in client components | Module boundaries are not enforced by default | Use the `server-only` package to cause a build error if server code is imported client-side |
| Hardcoding AWS region or account IDs | Quick local development hack | Use environment variables injected through ECS task definition |

---

## References

- Next.js App Router documentation: https://nextjs.org/docs/app
- Next.js standalone output: https://nextjs.org/docs/app/api-reference/config/next-config-js/output
- Prisma with Next.js best practices: https://www.prisma.io/docs/orm/more/help-and-troubleshooting/help-articles/nextjs-prisma-client-dev-practices
