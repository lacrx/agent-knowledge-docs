---
name: configure-prisma-postgres
title: Configure Prisma ORM for PostgreSQL
type: skill
topics:
  - prisma
  - postgres
  - nodejs
  - nextjs
  - database
  - aws
summary: >
  Configure Prisma ORM for PostgreSQL in a Node.js or Next.js application with
  schema definition, client generation, migration workflow, singleton pattern,
  and connection configuration for local development and AWS RDS/Aurora.
references:
  - skills/scaffold-nextjs-project.md
  - articles/aws/fargate/structuring-nextjs-server-for-fargate.md
  - articles/aws/nextjs-project-scaffolding-aws.md
last-updated: 2026-06-25
---

# Configure Prisma ORM for PostgreSQL

Set up Prisma ORM with PostgreSQL, including schema, client generation,
migrations, and connection patterns for local and AWS environments. Follow
steps in order.

---

## Prerequisites

- Node.js >= 18
- npm or pnpm package manager
- PostgreSQL database running locally or accessible via network
- For AWS: RDS or Aurora PostgreSQL instance provisioned with endpoint and credentials
- Project initialized with `package.json`

---

## Steps

### Step 1: Install Prisma dependencies

```bash
npm install prisma --save-dev
npm install @prisma/client
```

### Step 2: Initialize Prisma with PostgreSQL provider

```bash
npx prisma init --datasource-provider postgresql
```

This creates `prisma/schema.prisma` and a `.env` file. The `.env` file will
contain a placeholder `DATABASE_URL`.

### Step 3: Configure environment variables

Add the following to `.env` (never commit this file):

```bash
# Local development
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/myapp?schema=public"

# Shadow database for prisma migrate dev (can be same server, different db)
SHADOW_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/myapp_shadow?schema=public"
```

For AWS RDS/Aurora PostgreSQL, use the following format:

```bash
# AWS RDS connection string format
DATABASE_URL="postgresql://<username>:<password>@<rds-endpoint>:5432/<database>?schema=public&sslmode=require"

# Aurora PostgreSQL with IAM auth (use sslmode=verify-full in production)
DATABASE_URL="postgresql://<username>:<password>@<aurora-cluster-endpoint>:5432/<database>?schema=public&sslmode=verify-full&sslrootcert=/path/to/rds-ca-bundle.pem"

# With connection pooling (PgBouncer or RDS Proxy)
DATABASE_URL="postgresql://<username>:<password>@<rds-proxy-endpoint>:5432/<database>?schema=public&sslmode=require&pgbouncer=true&connection_limit=10"
```

Ensure `.env` is in `.gitignore`:

```bash
echo ".env" >> .gitignore
```

### Step 4: Define the Prisma schema

Edit `prisma/schema.prisma`:

```prisma
generator client {
  provider        = "prisma-client-js"
  previewFeatures = []
}

datasource db {
  provider          = "postgresql"
  url               = env("DATABASE_URL")
  shadowDatabaseUrl = env("SHADOW_DATABASE_URL")
}

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  posts     Post[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model Post {
  id        String   @id @default(cuid())
  title     String
  content   String?
  published Boolean  @default(false)
  author    User     @relation(fields: [authorId], references: [id])
  authorId  String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  @@index([authorId])
}
```

### Step 5: Validate and format the schema

```bash
npx prisma validate
npx prisma format
```

Always run these before creating a migration. `prisma validate` catches
schema errors and `prisma format` normalizes whitespace and ordering.

### Step 6: Create the first migration

```bash
npx prisma migrate dev --name init
```

This creates a migration file under `prisma/migrations/`, applies it to the
local database, and generates the Prisma Client.

### Step 7: Generate the Prisma Client

```bash
npx prisma generate
```

Run this after any schema change. In CI/CD, run it as part of the build step
so the generated client matches the deployed schema.

### Step 8: Create a reusable Prisma Client singleton

Create `lib/prisma.ts` (or `src/lib/prisma.ts` for Next.js):

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log:
      process.env.NODE_ENV === "development"
        ? ["query", "error", "warn"]
        : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
```

This singleton prevents exhausting database connections during development
when hot-reloading creates new `PrismaClient` instances.

### Step 9: Set up the local development database

For local development using Docker Compose, create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myapp
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  postgres-shadow:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myapp_shadow
    ports:
      - "5433:5432"
    volumes:
      - pgdata_shadow:/var/lib/postgresql/data

volumes:
  pgdata:
  pgdata_shadow:
```

Start the databases and run the migration:

```bash
docker compose up -d
npx prisma migrate dev
```

### Step 10: Add package.json scripts

```json
{
  "scripts": {
    "db:generate": "prisma generate",
    "db:migrate:dev": "prisma migrate dev",
    "db:migrate:deploy": "prisma migrate deploy",
    "db:push": "prisma db push",
    "db:seed": "prisma db seed",
    "db:studio": "prisma studio",
    "db:validate": "prisma validate && prisma format",
    "postinstall": "prisma generate"
  }
}
```

### Step 11: Set up production migration workflow

For production deployments (CI/CD pipeline or deploy script):

```bash
# 1. Validate the schema
npx prisma validate

# 2. Apply pending migrations (non-interactive, fails on drift)
npx prisma migrate deploy

# 3. Generate the client
npx prisma generate
```

Never run `prisma migrate dev` in production. Use `prisma migrate deploy`
which applies pending migrations without prompting or resetting data.

### Step 12: Configure SSL for AWS connections

For AWS RDS/Aurora connections that require SSL, download the CA bundle:

```bash
# Download the RDS CA bundle
curl -o prisma/rds-ca-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

Update the connection string in the deployment environment:

```bash
DATABASE_URL="postgresql://user:pass@mydb.cluster-xxxx.us-east-1.rds.amazonaws.com:5432/myapp?schema=public&sslmode=verify-full&sslrootcert=prisma/rds-ca-bundle.pem"
```

### Step 13: Commit and PR

```bash
git add prisma/schema.prisma prisma/migrations/ lib/prisma.ts docker-compose.yml package.json .gitignore
git commit -m "Configure Prisma ORM with PostgreSQL"
gh pr create --title "Configure Prisma ORM for PostgreSQL" --body "Adds Prisma schema, initial migration, client singleton, local dev database, and production migration workflow"
```

---

## Examples

### AWS RDS connection with connection pooling

```bash
# Using RDS Proxy for connection pooling
DATABASE_URL="postgresql://admin:secret@myapp-proxy.proxy-xxxx.us-east-1.rds.amazonaws.com:5432/myapp?schema=public&sslmode=require&pgbouncer=true&connection_limit=5"
```

### Next.js API route usage

```typescript
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

export async function GET() {
  const users = await prisma.user.findMany({
    include: { posts: { where: { published: true } } },
  });
  return NextResponse.json(users);
}
```

### Adding a migration after schema changes

```bash
# Edit prisma/schema.prisma, then:
npx prisma validate
npx prisma format
npx prisma migrate dev --name add_user_role
npx prisma generate
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use `postgresql` provider in datasource block | Prisma requires explicit provider; PostgreSQL enables full feature set including enums, JSON, and arrays |
| Keep `DATABASE_URL` and `SHADOW_DATABASE_URL` in environment variables only | Prevents credential leakage; `.env` must be in `.gitignore` |
| No secrets in committed files | Connection strings contain passwords; use env vars, SSM Parameter Store, or Secrets Manager |
| Run `prisma validate` and `prisma format` before every migration | Catches schema errors early and keeps formatting consistent |
| Use `prisma migrate deploy` in production (never `migrate dev`) | `migrate dev` can reset data and prompts interactively; `deploy` is non-interactive and safe |
| Keep Prisma Client as a singleton in app code | Prevents connection pool exhaustion during hot reload in development |
| Commit `prisma/migrations/` directory to version control | Migration history is the source of truth for database schema; required for `migrate deploy` |
| Use SSL (`sslmode=require` or `verify-full`) for AWS connections | Encrypts data in transit; `verify-full` validates the server certificate against the RDS CA bundle |
| Pin `@prisma/client` and `prisma` to the same version | Version mismatch between CLI and client causes generation errors |
| Include `prisma generate` in `postinstall` script | Ensures generated client is always in sync after `npm install` |

---

## Outputs

- Prisma schema file at `prisma/schema.prisma` with PostgreSQL provider
- Generated Prisma Client at `node_modules/.prisma/client/`
- Migration files under `prisma/migrations/`
- Reusable singleton client at `lib/prisma.ts`
- Migration command sequence: `validate` then `format` then `migrate dev` (local) or `migrate deploy` (production)
- Docker Compose configuration for local PostgreSQL and shadow database
- Package scripts for generate, migrate, deploy, seed, studio, and validate
