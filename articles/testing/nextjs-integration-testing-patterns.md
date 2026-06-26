---
title: Next.js Integration Testing Patterns
topics:
  - testing
  - nextjs
  - integration-testing
  - vitest
  - playwright
skills:
  - setup-nextjs-tests
summary: >
  Patterns and trade-offs for structuring Next.js integration tests with Vitest and Playwright, covering Server Component and API route testing, fixture strategy, AWS mock boundaries, test isolation, and CI reliability.
aliases:
  - nextjs integration tests
  - next.js test layers
  - react server component testing
related:
  - python-integration-testing-patterns
last-updated: 2026-06-25
---

# Next.js Integration Testing Patterns

## Overview

Next.js blurs the boundary between server and client in ways that affect testing strategy. Server Components, server actions, API route handlers, and client components each have different runtime contexts, which means a single test approach does not cover all boundaries. Without a deliberate plan, teams end up with slow Playwright suites testing things that Vitest could verify in milliseconds, or mocked-out unit tests that prove nothing about real data flow.

This article covers how to define test layers for Next.js projects, how to test each component type at the right level, how to manage fixtures and mocks for AWS-backed services, and how to structure CI pipelines for fast feedback. The goal is reliable tests that catch real bugs without burning CI minutes on redundant coverage.

> **Skill:** For step-by-step implementation including project setup and configuration files, use the `setup-nextjs-tests` skill.

---

## Test Layer Definitions

Define what each layer means before writing tests. The layers map differently in Next.js than in a traditional SPA because of the server-side rendering boundary.

| Layer        | Scope                                                     | Tools                    | Speed Target   |
|--------------|------------------------------------------------------------|--------------------------|----------------|
| Unit         | Single component or function, all dependencies mocked     | Vitest, Testing Library  | < 50 ms each   |
| Integration  | Multiple real modules working together (route + DB mock)  | Vitest, MSW, SDK mocks   | < 2 s each     |
| E2E          | Full running Next.js app, browser interaction             | Playwright               | < 30 s each    |

The key distinction: **unit tests replace all collaborators; integration tests exercise real module boundaries with controlled external dependencies.** An API route handler test that imports the real route function but mocks DynamoDB is an integration test for the route logic and a unit test for the AWS boundary. Be explicit about which boundary each test targets.

### Where each Next.js construct belongs

| Construct          | Unit                                        | Integration                                       | E2E                       |
|--------------------|---------------------------------------------|---------------------------------------------------|---------------------------|
| Server Component   | Await and render JSX, mock data fetches     | Render with real child components, mock API layer  | Full page load            |
| Client Component   | Render with Testing Library, mock callbacks | Render with real hooks and context providers       | User interaction flows    |
| API Route Handler  | Rarely useful at unit level                 | Import handler, call with `NextRequest`            | HTTP calls against server |
| Server Action      | Call function directly, mock side effects   | Call with real validation, mock persistence        | Form submission in browser|
| Middleware         | Call function with mock `NextRequest`       | Test redirect/rewrite behavior with real matchers  | Navigation-based          |

---

## Testing Server Components

Server Components are async functions that return JSX. They cannot use hooks or browser APIs. This makes them straightforward to test with Vitest, but the async nature requires a specific pattern.

### Direct invocation pattern

Call the component as a function, await the result, then render it:

```tsx
import { render, screen } from "@testing-library/react";
import { UserProfile } from "@/components/UserProfile";

it("renders user data from the database", async () => {
  // Mock the data layer, not the component
  vi.mock("@/lib/db", () => ({
    getUser: vi.fn().mockResolvedValue({ id: "1", name: "Alice" }),
  }));

  const jsx = await UserProfile({ userId: "1" });
  render(jsx);

  expect(screen.getByText("Alice")).toBeInTheDocument();
});
```

This works because Server Components are plain async functions outside the React Server Components protocol. The test runs in Node, not in a browser, which is exactly right for this boundary.

### What to mock

Mock the data-fetching layer (database queries, API calls), not the component itself. The test should verify that the component correctly transforms data into rendered output. If you mock the component, you are testing your mock.

---

## Testing Client Components

Client components use hooks, event handlers, and browser APIs. Test them with `@testing-library/react` and `userEvent`.

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchFilter } from "@/components/SearchFilter";

it("calls onFilter when the user submits", async () => {
  const onFilter = vi.fn();
  const user = userEvent.setup();

  render(<SearchFilter onFilter={onFilter} />);
  await user.type(screen.getByRole("textbox"), "query");
  await user.click(screen.getByRole("button", { name: /search/i }));

  expect(onFilter).toHaveBeenCalledWith("query");
});
```

For components that depend on React context (theme, auth, router), wrap them in a test provider rather than mocking `useContext`. A test utility that provides default context values reduces boilerplate:

```tsx
// test-utils.tsx
import { render, RenderOptions } from "@testing-library/react";
import { AuthProvider } from "@/providers/AuthProvider";

function AllProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider value={{ user: { id: "test", role: "admin" } }}>
      {children}
    </AuthProvider>
  );
}

export function renderWithProviders(
  ui: React.ReactElement,
  options?: Omit<RenderOptions, "wrapper">
) {
  return render(ui, { wrapper: AllProviders, ...options });
}
```

---

## Testing API Route Handlers

Next.js App Router API routes export named functions (`GET`, `POST`, etc.) that receive a `NextRequest` and return a `NextResponse`. Test them by importing the handler and calling it directly.

```typescript
import { NextRequest } from "next/server";
import { GET } from "@/app/api/items/[id]/route";

it("returns 200 with the item when found", async () => {
  mockDynamoGet({ id: "abc", title: "Widget" });

  const req = new NextRequest("http://localhost/api/items/abc");
  const res = await GET(req, { params: Promise.resolve({ id: "abc" }) });

  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.title).toBe("Widget");
});
```

This is an integration test: the real route handler code runs, including validation, error handling, and response formatting. Only the persistence layer is mocked. This catches bugs that unit tests of individual functions would miss, like incorrect status codes or malformed response bodies.

### Dynamic route params

In Next.js 15+, route params are provided as a `Promise`. Match this in tests:

```typescript
const params = Promise.resolve({ id: "abc", slug: "test" });
const res = await GET(req, { params });
```

Forgetting to wrap params in a Promise is a common source of test failures that do not reproduce in the running app.

---

## Testing Server Actions

Server actions are async functions marked with `"use server"`. They typically accept `FormData`, validate input, interact with a database, and call `revalidatePath` or `redirect`.

```typescript
import { createItem } from "@/app/actions/createItem";

it("returns validation error for empty title", async () => {
  const form = new FormData();
  form.set("title", "");

  const result = await createItem(form);

  expect(result.success).toBe(false);
  expect(result.errors).toContain("Title is required");
});
```

Server actions that call `redirect()` from `next/navigation` will throw. Mock the redirect to capture the target URL:

```typescript
import { redirect } from "next/navigation";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

it("redirects to the item page on success", async () => {
  mockDynamoPut();
  const form = new FormData();
  form.set("title", "New Item");

  await createItem(form);

  expect(redirect).toHaveBeenCalledWith("/items/mock-id");
});
```

Similarly, mock `revalidatePath` and `revalidateTag` to assert cache invalidation without triggering Next.js internals.

---

## Fixture Strategy

### MSW for HTTP boundaries

Use Mock Service Worker (MSW) to intercept HTTP requests at the network level. This is the right tool for mocking external APIs that your Next.js app calls during rendering or in API routes.

```typescript
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const server = setupServer(
  http.get("https://api.example.com/users/:id", ({ params }) => {
    return HttpResponse.json({ id: params.id, name: "Mock User" });
  })
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

Setting `onUnhandledRequest: "error"` catches unintended network calls. This is critical in integration tests where a missing mock means a test is hitting a real service.

### AWS SDK mocks for service boundaries

Use `aws-sdk-client-mock` to mock AWS SDK v3 clients. This intercepts at the SDK client level, which is more reliable than mocking HTTP calls to AWS endpoints.

```typescript
import { mockClient } from "aws-sdk-client-mock";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

const s3Mock = mockClient(S3Client);

beforeEach(() => s3Mock.reset());

it("handles S3 errors gracefully", async () => {
  s3Mock.on(GetObjectCommand).rejects(new Error("NoSuchKey"));

  const result = await fetchDocument("missing-key");
  expect(result).toBeNull();
});
```

### Factory functions over shared fixtures

Avoid a single `testItem` fixture shared across tests. Use factory functions that create fresh data:

```typescript
function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    id: crypto.randomUUID(),
    title: "Test Item",
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}
```

Factory functions prevent hidden coupling between tests. When test A modifies the shared fixture, test B breaks unpredictably.

---

## Test Isolation

### Reset state between tests

Every `afterEach` should restore mocks, clear MSW handlers, and clean up any DOM state:

```typescript
afterEach(() => {
  cleanup();           // @testing-library/react
  server.resetHandlers();  // MSW
  vi.restoreAllMocks();    // Vitest
  resetAwsMocks();         // aws-sdk-client-mock
});
```

Missing any of these resets is the most common cause of order-dependent test failures.

### Isolate module state with dynamic imports

Server actions and API routes often import singleton clients at module scope. Use `vi.mock` to replace these before the module loads, or use dynamic imports with `vi.resetModules()` to get a fresh module for each test:

```typescript
beforeEach(() => {
  vi.resetModules();
  resetAwsMocks();
});

it("test one", async () => {
  mockDynamoGet({ id: "1", title: "Found" });
  const { GET } = await import("@/app/api/items/[id]/route");
  // ...
});
```

This prevents leaking mock state from one test into another through module-level singletons.

---

## AWS-Aware Integration Boundaries

When your Next.js app depends on AWS services, define clear mock boundaries.

| Service      | Mock Approach              | When to Use                                     |
|-------------|----------------------------|--------------------------------------------------|
| DynamoDB    | `aws-sdk-client-mock`      | API routes and server actions that read/write     |
| S3          | `aws-sdk-client-mock`      | File upload/download handlers                     |
| SQS/SNS    | `aws-sdk-client-mock`      | Async event publishing from server actions        |
| Cognito     | MSW (mock token endpoints) | Auth flows in middleware or API routes            |
| External API| MSW                        | Any `fetch()` to third-party services             |

The principle: mock at the narrowest boundary that still exercises your code. `aws-sdk-client-mock` is narrower than MSW for AWS services because it intercepts at the SDK level, not the HTTP level. Use MSW for services accessed via `fetch()`.

For real AWS integration tests (e.g., validating IAM permissions or DynamoDB query patterns against a real table), gate them behind an environment variable:

```typescript
const SKIP_MSG = "Set AWS_INTEGRATION=1 to run";

describe.skipIf(!process.env.AWS_INTEGRATION)("DynamoDB integration", () => {
  it("queries with the expected index", async () => {
    // Uses real AWS credentials and a test table
  });
});
```

Never run real AWS tests in the default test command. They belong in a separate CI step with explicit opt-in.

---

## CI Strategy

### Pipeline structure

Run test layers in order of speed and cost:

1. **Lint and type check** (seconds) -- `next lint` and `tsc --noEmit` catch errors before any test runs
2. **Unit tests** (seconds) -- Vitest with mocked dependencies, no network
3. **Integration tests** (seconds to minutes) -- Vitest with MSW and SDK mocks
4. **E2E tests** (minutes) -- Playwright against a built Next.js app
5. **AWS integration tests** (minutes, optional) -- real AWS, gated by environment variable

If unit tests fail, skip downstream layers to save CI minutes.

### Vitest project configuration for layer separation

Use Vitest workspace or include/exclude patterns to run layers independently:

```typescript
// vitest.config.ts
export default defineConfig({
  test: {
    include: [
      "tests/unit/**/*.test.{ts,tsx}",
      "tests/integration/**/*.test.{ts,tsx}",
    ],
    exclude: ["tests/e2e/**"],
  },
});
```

### Playwright CI considerations

Playwright in CI requires a built and running Next.js app. Build once, serve with `next start`, and wait for the server:

```yaml
- run: npm run build
- run: |
    npm run start &
    npx wait-on http://localhost:3000
- run: npx playwright test
```

Use `forbidOnly: !!process.env.CI` in `playwright.config.ts` to prevent `.only` tests from passing in CI. Set `retries: 2` in CI to handle transient browser-level flakes.

### Test tagging

Vitest does not have pytest-style markers, but you can use file organization and glob patterns as an equivalent:

```bash
vitest run --include "tests/unit/**"          # unit only
vitest run --include "tests/integration/**"   # integration only
vitest run                                     # both
```

For finer-grained control, use `describe.skip`, `describe.skipIf`, or Vitest's `test.each` with environment-driven flags.

---

## Flake Reduction

Flaky tests in Next.js projects usually come from a small set of causes:

| Cause                                  | Fix                                                              |
|----------------------------------------|------------------------------------------------------------------|
| Unhandled MSW requests                 | Set `onUnhandledRequest: "error"` to catch missing mocks         |
| Module-level singleton leaking state   | Use `vi.resetModules()` and dynamic imports                      |
| Playwright timing on hydration         | Use `waitFor` or Playwright auto-waiting locators, not `sleep`   |
| Missing `cleanup()` in afterEach       | Always call `cleanup()` from `@testing-library/react`            |
| Port conflicts in CI                   | Use `0` for dynamic port or coordinate via env vars              |
| Shared mock state across tests         | Reset all mocks in `afterEach`, including AWS SDK mocks          |
| Race conditions in async component tests | Always `await` component rendering; use `findBy` over `getBy`  |
| Flaky Playwright selectors             | Prefer `getByRole` and `getByText` over CSS selectors            |

For Playwright specifically, use `test.describe.serial()` only when tests genuinely depend on each other (e.g., create-then-read flows). Otherwise, keep tests independent and run with `fullyParallel: true`.

---

## Directory Structure

Organize tests to mirror the layer strategy:

```
tests/
  setup.ts                    # MSW server lifecycle, global cleanup
  __mocks__/
    msw-handlers.ts           # Default MSW handlers for API mocking
    aws-clients.ts            # AWS SDK mock setup and reset helpers
  unit/
    components/
      ServerGreeting.test.tsx # Server Component direct-invocation tests
      Counter.test.tsx        # Client Component interaction tests
    actions/
      createItem.test.ts      # Server Action logic tests
  integration/
    api/
      items.test.ts           # API route handler tests
      auth.test.ts            # Auth middleware integration tests
  e2e/
    home.spec.ts              # Playwright page-level tests
    item-crud.spec.ts         # Playwright workflow tests
  test-utils.tsx              # Shared render helpers, providers
  factories.ts                # Factory functions for test data
```

Each layer directory can have its own setup if needed. Shared utilities live at the `tests/` root.

---

## Common Mistakes

| Mistake                                            | Why It Hurts                                                         |
|----------------------------------------------------|----------------------------------------------------------------------|
| Testing Server Components in Playwright            | Slow; Vitest can verify the same rendering logic in milliseconds     |
| Mocking the component you are testing              | Proves nothing; the mock passes, production breaks                   |
| Forgetting `vi.resetModules()` with dynamic imports| Module-level mock state leaks between tests                          |
| Using `getBy` for async content                    | Fails intermittently; use `findBy` which polls until found           |
| Hard-coding `localhost:3000` in tests              | Breaks when CI uses a different port                                 |
| Not mocking `redirect()` in server action tests    | Test throws and fails instead of asserting the redirect target       |
| Sharing a mock database client across test files   | Order-dependent failures when running in parallel                    |
| Skipping MSW `resetHandlers()` in afterEach        | One test's mock response leaks into the next test                    |
| Running e2e tests against dev server in CI         | Dev server is slow and includes HMR overhead; use `next build` + `next start` |

---

## Trade-offs

**Vitest vs. Jest:** Vitest has native ESM support, first-class TypeScript handling, and shares configuration patterns with Vite. Jest requires additional transform configuration for Next.js. If your project already uses Jest and it works, the migration cost may not be worth it. For new projects, Vitest is the simpler choice.

**MSW vs. mocking fetch directly:** MSW intercepts at the network layer, which means your code's actual `fetch` calls run. Mocking `global.fetch` with `vi.fn()` is simpler but skips request construction, headers, and error handling. Use MSW for integration tests; use `vi.fn()` only for isolated unit tests where the fetch behavior is not the concern.

**Direct handler invocation vs. HTTP-level testing:** Importing and calling an API route handler directly is faster and requires no running server. Testing via HTTP against a running Next.js app catches middleware, routing, and serialization bugs. Use direct invocation for most tests; add a small number of HTTP-level e2e tests for critical paths.

**Mocking AWS SDK vs. LocalStack:** `aws-sdk-client-mock` is fast, requires no infrastructure, and works in any CI environment. LocalStack provides higher fidelity but adds container startup time and configuration complexity. Default to SDK mocks; use LocalStack only when you need to test multi-service interactions (e.g., S3 event triggering a Lambda that writes to DynamoDB).

**Parallel vs. sequential Playwright tests:** `fullyParallel: true` is faster but requires tests to be fully independent. If tests share server-side state (e.g., a seeded database), parallel execution causes race conditions. Start with parallel and add serialization only where tests genuinely depend on shared state.

---

## Related Articles

- **[python-integration-testing-patterns](../testing/python-integration-testing-patterns.md)** -- Equivalent patterns for Python projects using pytest, covering fixture strategy and AWS mocking.
