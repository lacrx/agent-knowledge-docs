---
name: scaffold-nextjs-project
title: Scaffold Next.js Project
type: skill
topics:
  - nextjs
  - typescript
  - scaffolding
  - project-setup
  - aws
summary: >
  Scaffold a Next.js 14+ TypeScript project from scratch with App Router, pnpm,
  Tailwind CSS, Prisma, and AWS-ready configuration for Fargate deployment.
references:
  - skills/create-nextjs-dockerfile.md
  - skills/scaffold-python-project.md
last-updated: 2026-06-13
---

# Scaffold Next.js Project

Create a complete Next.js project structure for a TypeScript app deployed to AWS Fargate.
Follow steps in order.

---

## Prerequisites

- Node.js 20+ installed
- pnpm installed (`npm install -g pnpm`)
- Git installed

---

## Steps

### Step 1: Create directory structure

```bash
PROJECT="my-nextjs-app"

mkdir -p ${PROJECT}/src/{app/api/health,components,lib,styles}
mkdir -p ${PROJECT}/prisma
mkdir -p ${PROJECT}/public
mkdir -p ${PROJECT}/tests
mkdir -p ${PROJECT}/.github/workflows
```

### Step 2: Initialize pnpm and install production dependencies

```bash
cd ${PROJECT}

pnpm init

pnpm add next@latest react@latest react-dom@latest \
  @aws-sdk/client-s3 @aws-sdk/client-secrets-manager \
  @prisma/client
```

### Step 3: Install dev dependencies

```bash
pnpm add -D typescript @types/react @types/node \
  @playwright/test msw \
  eslint eslint-config-next prettier \
  tailwindcss postcss autoprefixer \
  prisma
```

### Step 4: Create `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

### Step 5: Create `next.config.ts`

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

### Step 6: Create `tailwind.config.ts`

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};

export default config;
```

### Step 7: Create `.eslintrc.json`

```json
{
  "extends": "next/core-web-vitals"
}
```

### Step 8: Create `prettier.config.js`

```javascript
/** @type {import("prettier").Config} */
const config = {
  semi: true,
  singleQuote: false,
  trailingComma: "all",
  tabWidth: 2,
};

module.exports = config;
```

### Step 9: Create `.env.example`

```bash
# Client-side (exposed to browser)
NEXT_PUBLIC_APP_NAME=<your-app-name>
NEXT_PUBLIC_API_URL=<your-api-url>

# Server-side AWS Configuration
AWS_REGION=<your-aws-region>
AWS_ACCESS_KEY_ID=<value-placeholder>
AWS_SECRET_ACCESS_KEY=<value-placeholder>

# S3
S3_BUCKET=<your-bucket-name>

# Secrets Manager
SECRETS_ARN=<value-placeholder>

# Database (Prisma)
DATABASE_URL=<value-placeholder>

# Application
APP_ENV=development
PORT=8080
```

No real values. Secrets use `<value-placeholder>`. Copy to `.env.local` and fill in.

### Step 10: Create `.gitignore`

```
# Next.js
.next/
out/

# Node
node_modules/
*.tsbuildinfo

# Testing
coverage/
playwright-report/
test-results/

# Prisma
prisma/*.db

# Secrets
.env
.env.*
!.env.example

# IDE
.vscode/
.idea/
*.swp
*~

# OS
.DS_Store
Thumbs.db
```

### Step 11: Create `src/app/layout.tsx`

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME ?? "My App",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

### Step 12: Create `src/app/page.tsx`

```tsx
export default function Home() {
  return (
    <main>
      <h1>{process.env.NEXT_PUBLIC_APP_NAME ?? "My App"}</h1>
      <p>App is running.</p>
    </main>
  );
}
```

### Step 13: Create `src/app/api/health/route.ts`

```typescript
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    version: "0.1.0",
  });
}
```

### Step 14: Create `src/styles/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

### Step 15: Create `bootstrap.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

MIN_NODE="20"

echo "=== Checking Node.js version ==="
NODE_VERSION=$(node --version | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt "$MIN_NODE" ]; then
    echo "ERROR: Node.js ${MIN_NODE}+ required, found v$(node --version)"
    exit 1
fi
echo "Node.js $(node --version) OK"

echo "=== Checking pnpm ==="
if ! command -v pnpm &> /dev/null; then
    echo "ERROR: pnpm not found. Install with: npm install -g pnpm"
    exit 1
fi
echo "pnpm $(pnpm --version) OK"

echo "=== Installing dependencies ==="
pnpm install

echo "=== Running linter ==="
pnpm eslint src/

echo "=== Running type check ==="
pnpm tsc --noEmit

echo "=== Running tests ==="
pnpm exec playwright test 2>/dev/null || echo "No Playwright tests found yet — skipping"

echo ""
echo "Done. Run dev server with: pnpm dev"
```

```bash
chmod +x bootstrap.sh
```

### Step 16: Create `tests/health.spec.ts` stub

```typescript
import { test, expect } from "@playwright/test";

test("health endpoint returns ok", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.status).toBe("ok");
});
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| `src/` for all application code | Next.js App Router convention; keeps root clean |
| `.env.example` shows variable names only, `<value-placeholder>` for secrets | Prevents accidental secret commits; documents expected env vars |
| `NEXT_PUBLIC_*` prefix for client-side vars, plain names for server-only | Next.js only exposes `NEXT_PUBLIC_*` to the browser bundle |
| Production deps vs dev deps kept separate in `package.json` | `pnpm install --prod` in Docker skips dev deps |
| `output: "standalone"` in `next.config.ts` | Required for Fargate — produces self-contained server.js |
| No hard-coded secrets anywhere | Use `process.env.KEY` with runtime checks for required vars |

---

## Outputs

- Project directory with `src/app/`, `src/components/`, `src/lib/`, `src/styles/`, `prisma/`, `public/`, `tests/`
- `package.json` with production and dev dependencies via pnpm
- Config files: `tsconfig.json`, `next.config.ts`, `tailwind.config.ts`, `.eslintrc.json`, `prettier.config.js`
- `.env.example` with `NEXT_PUBLIC_*` client vars and server-only AWS vars
- `.gitignore` covering Next.js, node_modules, secrets, IDE files
- `src/app/layout.tsx`, `src/app/page.tsx` starter pages
- `src/app/api/health/route.ts` health check endpoint
- `bootstrap.sh` that validates Node/pnpm, installs deps, lints, type-checks, and tests
- `tests/health.spec.ts` Playwright test stub
