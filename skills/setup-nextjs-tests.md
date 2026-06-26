---
name: setup-nextjs-tests
title: Set Up Next.js Test Infrastructure
type: skill
topics:
  - testing
  - nextjs
  - vitest
  - playwright
  - ci
summary: >
  Set up test infrastructure for a Next.js application with Vitest for unit and
  component tests, Playwright for end-to-end tests, AWS mock patterns, and
  repeatable local and CI test commands.
references:
  - skills/scaffold-nextjs-project.md
  - articles/testing/nextjs-integration-testing-patterns.md
last-updated: 2026-06-25
---

# Set Up Next.js Test Infrastructure

Configure unit, component, integration, and end-to-end tests for a Next.js
application. Uses Vitest for fast unit/component/integration tests and Playwright
for browser-based e2e tests. Includes mocking patterns for AWS-backed APIs and
server actions. Follow steps in order.

---

## Prerequisites

- Node.js >= `${node_version}` installed
- Next.js project initialized with `${package_manager}` as package manager
- `${test_directory}` directory does not yet exist or is empty
- AWS credentials are NOT required (all AWS calls are mocked)

---

## Steps

### Step 1: Install test dependencies

```bash
# Unit / component / integration test tooling
${package_manager} add -D vitest @vitejs/plugin-react jsdom @testing-library/react \
  @testing-library/jest-dom @testing-library/user-event msw aws-sdk-client-mock

# End-to-end test tooling
${package_manager} add -D @playwright/test
npx playwright install --with-deps chromium
```

### Step 2: Create the Vitest configuration

Create `vitest.config.ts` in the project root.

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./${test_directory}/setup.ts"],
    include: [
      "${test_directory}/unit/**/*.test.{ts,tsx}",
      "${test_directory}/integration/**/*.test.{ts,tsx}",
    ],
    exclude: ["${test_directory}/e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "json-summary"],
      thresholds: {
        statements: ${coverage_target},
        branches: ${coverage_target},
        functions: ${coverage_target},
        lines: ${coverage_target},
      },
    },
    testTimeout: ${test_timeout_ms},
  },
});
```

### Step 3: Create the test setup file

Create `${test_directory}/setup.ts`.

```typescript
// ${test_directory}/setup.ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, afterAll } from "vitest";
import { server } from "./__mocks__/msw-handlers";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
```

### Step 4: Create test directory structure

```bash
mkdir -p ${test_directory}/unit/components
mkdir -p ${test_directory}/unit/actions
mkdir -p ${test_directory}/integration/api
mkdir -p ${test_directory}/e2e
mkdir -p ${test_directory}/__mocks__
```

### Step 5: Create MSW mock handlers for API routes

Create `${test_directory}/__mocks__/msw-handlers.ts`.

```typescript
// ${test_directory}/__mocks__/msw-handlers.ts
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const API_BASE = "${mock_api_base_url}";

export const handlers = [
  http.get(`${API_BASE}/api/health`, () => {
    return HttpResponse.json({ status: "ok" });
  }),

  http.post(`${API_BASE}/api/items`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ id: "mock-id", ...body }, { status: 201 });
  }),
];

export const server = setupServer(...handlers);
```

### Step 6: Create AWS SDK mock utilities

Create `${test_directory}/__mocks__/aws-clients.ts`.

```typescript
// ${test_directory}/__mocks__/aws-clients.ts
import { mockClient } from "aws-sdk-client-mock";
import { DynamoDBDocumentClient, GetCommand, PutCommand } from "@aws-sdk/lib-dynamodb";

export const ddbMock = mockClient(DynamoDBDocumentClient);

export function mockDynamoGet(item: Record<string, unknown> | undefined) {
  ddbMock.on(GetCommand).resolves({ Item: item });
}

export function mockDynamoPut() {
  ddbMock.on(PutCommand).resolves({});
}

// Add additional AWS client mocks here (S3, SQS, etc.) following the same pattern:
// export const s3Mock = mockClient(S3Client);

export function resetAwsMocks() {
  ddbMock.reset();
}
```

### Step 7: Write a Server Component test example

Create `${test_directory}/unit/components/ServerGreeting.test.tsx`.

```tsx
// ${test_directory}/unit/components/ServerGreeting.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ServerGreeting } from "@/components/ServerGreeting";

// Server Components are async functions returning JSX. Await then render.
describe("ServerGreeting", () => {
  it("renders a greeting with the provided name", async () => {
    const jsx = await ServerGreeting({ name: "Alice" });
    render(jsx);
    expect(screen.getByText(/hello, alice/i)).toBeInTheDocument();
  });
});
```

### Step 8: Write a Client Component test example

Create `${test_directory}/unit/components/Counter.test.tsx`.

```tsx
// ${test_directory}/unit/components/Counter.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Counter } from "@/components/Counter";

describe("Counter", () => {
  it("increments count on button click", async () => {
    const user = userEvent.setup();
    render(<Counter initialCount={0} />);

    expect(screen.getByText("Count: 0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /increment/i }));

    expect(screen.getByText("Count: 1")).toBeInTheDocument();
  });
});
```

### Step 9: Write a Server Action test example

Create `${test_directory}/unit/actions/createItem.test.ts`.

```typescript
// ${test_directory}/unit/actions/createItem.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mockDynamoPut, resetAwsMocks } from "../../__mocks__/aws-clients";

// Mock the module that creates the DynamoDB client
vi.mock("@/lib/dynamodb", () => ({
  docClient: {},
}));

describe("createItem server action", () => {
  beforeEach(() => {
    resetAwsMocks();
  });

  it("inserts an item and returns success", async () => {
    mockDynamoPut();
    const { createItem } = await import("@/app/actions/createItem");

    const formData = new FormData();
    formData.set("title", "Test Item");
    formData.set("description", "A test description");

    const result = await createItem(formData);

    expect(result).toEqual(
      expect.objectContaining({ success: true }),
    );
  });
});
```

### Step 10: Write an API route integration test example

Create `${test_directory}/integration/api/items.test.ts`.

```typescript
// ${test_directory}/integration/api/items.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { NextRequest } from "next/server";
import { mockDynamoGet, resetAwsMocks } from "../../__mocks__/aws-clients";

describe("GET /api/items/[id]", () => {
  beforeEach(() => {
    resetAwsMocks();
  });

  it("returns 200 with item data when item exists", async () => {
    mockDynamoGet({ id: "abc-123", title: "Found Item" });

    const { GET } = await import("@/app/api/items/[id]/route");
    const req = new NextRequest("http://localhost:3000/api/items/abc-123");
    const res = await GET(req, { params: Promise.resolve({ id: "abc-123" }) });

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.title).toBe("Found Item");
  });

  it("returns 404 when item does not exist", async () => {
    mockDynamoGet(undefined);

    const { GET } = await import("@/app/api/items/[id]/route");
    const req = new NextRequest("http://localhost:3000/api/items/missing");
    const res = await GET(req, { params: Promise.resolve({ id: "missing" }) });

    expect(res.status).toBe(404);
  });
});
```

### Step 11: Create the Playwright configuration

Create `playwright.config.ts` in the project root.

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./${test_directory}/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "html",
  timeout: ${test_timeout_ms},

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "${playwright_base_url}",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  webServer: process.env.CI
    ? undefined
    : {
        command: "${package_manager} run dev",
        url: "${playwright_base_url}",
        reuseExistingServer: true,
        timeout: 30_000,
      },
});
```

### Step 12: Write an e2e test example

Create `${test_directory}/e2e/home.spec.ts`.

```typescript
// ${test_directory}/e2e/home.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Home page", () => {
  test("renders heading and navigates to about", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    await page.getByRole("link", { name: /about/i }).click();
    await expect(page).toHaveURL(/\/about/);
  });
});
```

### Step 13: Create the test environment file

Create `${env_file_path}`.

```bash
# ${env_file_path}
# Test-only environment variables. Never commit real secrets.
AWS_REGION="${aws_region}"
AWS_ACCESS_KEY_ID="test-key"
AWS_SECRET_ACCESS_KEY="test-secret"
NEXT_PUBLIC_API_URL="${mock_api_base_url}"
DATABASE_URL="postgresql://test:test@localhost:5432/testdb"
```

Add the env file to `.gitignore` if it contains `.local`:

```bash
echo "${env_file_path}" >> .gitignore
```

### Step 14: Add test scripts to package.json

```bash
# Add scripts using npm pkg set (works with npm, adaptable for other managers)
npm pkg set scripts.test="${package_manager} run test:unit"
npm pkg set scripts.test:unit="vitest run"
npm pkg set scripts.test:unit:watch="vitest"
npm pkg set scripts.test:integration="vitest run --project integration"
npm pkg set scripts.test:e2e="playwright test"
npm pkg set scripts.test:e2e:ui="playwright test --ui"
npm pkg set scripts.test:coverage="vitest run --coverage"
npm pkg set scripts.test:ci="${package_manager} run test:unit && ${package_manager} run test:e2e"
```

### Step 15: Create CI test workflow

Create `.github/workflows/test.yml`.

```yaml
name: Test

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

env:
  AWS_REGION: "${aws_region}"
  AWS_ACCESS_KEY_ID: "test-key"
  AWS_SECRET_ACCESS_KEY: "test-secret"
  NEXT_PUBLIC_API_URL: "${ci_base_url}"

jobs:
  unit-and-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "${node_version}"
          cache: "${package_manager}"
      - run: ${package_manager} install
      - run: ${package_manager} run test:unit
      - run: ${package_manager} run test:coverage
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage/

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "${node_version}"
          cache: "${package_manager}"
      - run: ${package_manager} install
      - run: npx playwright install --with-deps chromium
      - run: ${package_manager} run build
        env:
          NEXT_PUBLIC_API_URL: "${ci_base_url}"
      - run: |
          ${package_manager} run start &
          npx wait-on ${ci_base_url}
        env:
          PORT: "3000"
      - run: PLAYWRIGHT_BASE_URL="${ci_base_url}" ${package_manager} run test:e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

### Step 16: Run tests locally to verify

```bash
${package_manager} run test:unit        # unit and component tests
${package_manager} run test:coverage    # unit tests with coverage report
${package_manager} run test:e2e         # e2e tests (starts dev server)
${package_manager} run test:ci          # full suite as CI would run it
```

### Step 17: Commit and open PR

```bash
git add vitest.config.ts playwright.config.ts ${test_directory}/ \
  .github/workflows/test.yml package.json
git commit -m "Add test infrastructure: Vitest, Playwright, AWS mocks, CI workflow"
gh pr create --title "Set up test infrastructure" \
  --body "Adds Vitest for unit/component/integration tests, Playwright for e2e, AWS SDK mocks, MSW API mocks, and CI workflow"
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use Vitest for unit/component tests, Playwright for e2e | Vitest has native ESM and TypeScript support matching Next.js; Playwright handles JS-rendered pages reliably |
| Separate unit, integration, and e2e directories | Clear boundaries prevent slow tests from blocking fast feedback loops |
| No secrets in committed test config files | Use environment variable placeholders; real values live in CI secrets or local `.env` files excluded via `.gitignore` |
| Mock AWS dependencies by default | Tests must run without AWS credentials; `aws-sdk-client-mock` intercepts SDK calls at the client level |
| Mock external APIs with MSW | `msw` intercepts at the network level, keeping tests isolated from real services |
| Include both local and CI test commands | Developers run `test:unit` locally for fast feedback; CI runs full suite including e2e |
| Keep tests deterministic and isolated | Each test resets mocks in `beforeEach`/`afterEach`; no shared mutable state between tests |
| Use environment variable placeholders only in example config | Prevents leaking real credentials; makes the skill reusable across projects |
| Pin test timeouts via `${test_timeout_ms}` variable | Prevents flaky tests from hanging indefinitely in CI |

---

## Outputs

- `vitest.config.ts` -- unit and integration test configuration with coverage thresholds
- `playwright.config.ts` -- e2e test configuration with CI-aware settings
- `${test_directory}/setup.ts` -- global test setup with MSW server lifecycle
- `${test_directory}/__mocks__/msw-handlers.ts` -- MSW handlers for API route mocking
- `${test_directory}/__mocks__/aws-clients.ts` -- AWS SDK mock utilities for DynamoDB and S3
- `${test_directory}/unit/` -- unit test examples for Server Components, client components, and server actions
- `${test_directory}/integration/` -- integration test examples for API routes
- `${test_directory}/e2e/` -- Playwright e2e test examples
- `.github/workflows/test.yml` -- CI workflow running unit, integration, coverage, and e2e tests
- Test commands: `test:unit`, `test:unit:watch`, `test:integration`, `test:e2e`, `test:e2e:ui`, `test:coverage`, `test:ci`
