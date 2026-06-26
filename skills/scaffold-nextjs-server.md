---
name: scaffold-nextjs-server
title: Scaffold Next.js Server
type: skill
topics:
  - nextjs
  - typescript
  - scaffolding
  - prisma
  - fargate
  - aws
summary: >
  Scaffold a full-stack Next.js App Router application with SSR, server components,
  API routes, Prisma/Postgres, Docker standalone build, and local docker-compose dev.
references:
  - skills/scaffold-nextjs-project.md
  - skills/create-nextjs-dockerfile.md
  - articles/aws/fargate/deploying-nextjs-apps-to-fargate.md
  - articles/aws/fargate/structuring-nextjs-server-for-fargate.md
  - articles/aws/nextjs-project-scaffolding-aws.md
last-updated: 2026-06-13
---

# Scaffold Next.js Server

Create a full-stack Next.js application with server-side rendering, server/client
component patterns, Prisma database access, and Docker deployment for AWS Fargate.
Follow steps in order.

---

## Prerequisites

- Node.js 20+ installed
- pnpm installed (`npm install -g pnpm`)
- PostgreSQL available (local install or RDS instance)
- Project name decided
- Git installed

---

## Steps

### Step 1: Create project with create-next-app

```bash
PROJECT="my-app"

pnpm create next-app ${PROJECT} \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --no-import-alias

cd ${PROJECT}
```

### Step 2: Configure `next.config.ts`

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    serverActions: {
      bodySizeLimit: "2mb",
    },
  },
};

export default nextConfig;
```

`output: "standalone"` is required — Fargate runs the built output, not `next dev`.

### Step 3: Create `src/app/layout.tsx`

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME ?? "My App",
  description: "Full-stack Next.js application",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white antialiased">{children}</body>
    </html>
  );
}
```

This is a server component by default. No `"use client"` needed.

### Step 4: Create `src/app/page.tsx` (server component)

```tsx
import { db } from "@/lib/db";

export default async function Home() {
  const userCount = await db.user.count();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold">
        {process.env.NEXT_PUBLIC_APP_NAME ?? "My App"}
      </h1>
      <p className="mt-4 text-gray-600">
        {userCount} registered user{userCount !== 1 ? "s" : ""}
      </p>
    </main>
  );
}
```

Server component — database query runs at request time on the server, never
shipped to the browser.

### Step 5: Create `src/app/api/health/route.ts`

```typescript
import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    await db.$queryRaw`SELECT 1`;
    return NextResponse.json({ status: "healthy", version: "0.1.0" });
  } catch {
    return NextResponse.json(
      { status: "unhealthy", version: "0.1.0" },
      { status: 503 },
    );
  }
}
```

ALB health check target. Returns JSON only — API routes never render HTML.

### Step 6: Create `src/app/dashboard/page.tsx` (client component)

```tsx
"use client";

import { useState, useEffect } from "react";

export default function Dashboard() {
  const [data, setData] = useState<{ status: string } | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then(setData);
  }, []);

  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="mt-4 text-gray-600">
        Server status: {data?.status ?? "loading..."}
      </p>
    </main>
  );
}
```

`"use client"` directive — this page uses `useState` and `useEffect` (browser APIs).
Only add this when you need interactivity.

### Step 7: Set up Prisma

```bash
pnpm add prisma @prisma/client
pnpm exec prisma init
```

Replace `prisma/schema.prisma`:

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  @@map("users")
}

model AuditLog {
  id        String   @id @default(cuid())
  action    String
  entity    String
  entityId  String   @map("entity_id")
  payload   Json?
  createdAt DateTime @default(now()) @map("created_at")

  @@index([entity, entityId])
  @@map("audit_logs")
}
```

Create `src/lib/db.ts` — singleton PrismaClient:

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const db = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = db;
}
```

Singleton prevents connection exhaustion. In development, the client survives
hot reloads via `globalThis`. In production, a single instance is created.

### Step 8: Create `src/lib/env.ts`

```typescript
function required(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

export const env = {
  DATABASE_URL: required("DATABASE_URL"),
  NODE_ENV: process.env.NODE_ENV ?? "development",
  PORT: process.env.PORT ?? "3000",
  APP_URL: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
  AWS_REGION: process.env.AWS_REGION ?? "us-east-1",
  S3_BUCKET: process.env.S3_BUCKET,
} as const;
```

Fails fast at startup if `DATABASE_URL` is missing. Optional vars use fallback.

### Step 9: Create component boundary examples

`src/components/server-status.tsx` — server component (default):

```tsx
import { db } from "@/lib/db";

export async function ServerStatus() {
  const count = await db.user.count();

  return (
    <div className="rounded border p-4">
      <h2 className="font-semibold">Server Component</h2>
      <p className="text-sm text-gray-600">
        This runs on the server. DB query result: {count} users.
      </p>
    </div>
  );
}
```

`src/components/click-counter.tsx` — client component:

```tsx
"use client";

import { useState } from "react";

export function ClickCounter() {
  const [count, setCount] = useState(0);

  return (
    <div className="rounded border p-4">
      <h2 className="font-semibold">Client Component</h2>
      <p className="text-sm text-gray-600">
        This runs in the browser. Clicks: {count}
      </p>
      <button
        onClick={() => setCount((c) => c + 1)}
        className="mt-2 rounded bg-blue-500 px-3 py-1 text-white"
      >
        Click me
      </button>
    </div>
  );
}
```

Pattern: server components are the default. Only add `"use client"` when you
need `useState`, `useEffect`, event handlers, or browser APIs.

### Step 10: Create `.env.example`

```bash
# Database (Prisma)
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>?schema=public

# Client-side (exposed to browser)
NEXT_PUBLIC_APP_NAME=<your-app-name>
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Server-side AWS Configuration
AWS_REGION=<your-aws-region>
AWS_ACCESS_KEY_ID=<value-placeholder>
AWS_SECRET_ACCESS_KEY=<value-placeholder>

# S3
S3_BUCKET=<your-bucket-name>

# Application
NODE_ENV=development
PORT=3000
```

Copy to `.env` and fill in. `NEXT_PUBLIC_*` vars are exposed to the browser
bundle. All others are server-only.

### Step 11: Create Dockerfile (multi-stage standalone)

```dockerfile
# ── Dependencies ───────────────────────────────────────────────
FROM node:20-slim AS deps

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile

# ── Builder ────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN corepack enable pnpm && \
    pnpm exec prisma generate && \
    pnpm run build

# ── Runtime ────────────────────────────────────────────────────
FROM node:20-slim

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.next/standalone ./
COPY --from=builder --chown=appuser:appuser /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:appuser /app/public ./public
COPY --from=builder --chown=appuser:appuser /app/node_modules/.prisma ./node_modules/.prisma

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/api/health').then(r=>{if(!r.ok)process.exit(1)})" || exit 1

CMD ["node", "server.js"]
```

Key: Prisma generated client is copied separately — standalone output does not
include it. Port 3000 is Next.js default; mapped in ECS task definition.

### Step 12: Create `.dockerignore`

```
.git
.gitignore
.next
node_modules
.env
.env.*
!.env.example
prisma/migrations
tests/
*.md
docker-compose*.yml
.eslintrc*
.prettierrc*
coverage/
.vscode
.idea
```

### Step 13: Create `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myapp_dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/myapp_dev?schema=public
      NODE_ENV: production
    depends_on:
      - db

volumes:
  pgdata:
```

Local dev: `docker compose up`. App builds and connects to Postgres.

---

## Constraints

| Constraint | Rationale |
|---|---|
| `output: "standalone"` required | Fargate runs the built output, not `next dev` |
| PrismaClient must be a singleton | Prevents connection exhaustion in server component re-renders |
| Server components by default | Only add `"use client"` for browser APIs or interactivity |
| API routes return JSON only | `src/app/api/` routes never render HTML |
| `.env.example` lists names only, placeholders for secrets | Prevents accidental secret commits |
| No secrets in Docker image | Use ECS task definition `secrets` from Secrets Manager |
| Health endpoint at `/api/health` | ALB health check target; must return 200 |
| Port 3000 | Next.js default; mapped in Fargate task definition |

---

## Outputs

- Working Next.js app with standalone build
- Prisma configured with example schema (`User`, `AuditLog` models)
- Docker build succeeds: `docker build -t my-app .`
- `/api/health` returns 200 with database connectivity check
- Server and client component examples demonstrating the boundary
- Local dev works: `docker compose up`
- `src/lib/db.ts` singleton PrismaClient
- `src/lib/env.ts` typed env access with fail-fast on missing required vars
