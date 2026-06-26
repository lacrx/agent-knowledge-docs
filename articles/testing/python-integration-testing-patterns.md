---
title: Python Integration Testing Patterns
topics:
  - testing
  - python
  - integration-testing
  - pytest
  - aws
skills:
  - setup-python-integration-tests
summary: >
  Patterns and trade-offs for structuring Python integration tests with pytest, covering fixture strategy, test boundaries, AWS-aware mocking, containerized dependencies, and CI reliability.
aliases:
  - python integration tests
  - pytest integration testing
  - python test layers
related:
  - testing-aws-services-with-moto
last-updated: 2026-06-25
---

# Python Integration Testing Patterns

## Overview

Integration tests verify that multiple components work together correctly. In Python projects, the line between unit tests and integration tests is often blurry, which leads to slow CI pipelines, flaky runs, and tests that mock so aggressively they prove nothing. Having a deliberate strategy for test boundaries, fixtures, and environment management prevents these problems.

This article covers how to think about test layers, how to structure pytest fixtures for integration tests, when to use mocks versus real dependencies, and how to keep integration tests reliable in CI. AWS-specific patterns are included because cloud service boundaries are a common source of integration test complexity.

> **Skill:** For step-by-step implementation including project setup and configuration files, use the `setup-python-integration-tests` skill.

---

## Test Layer Definitions

Before writing integration tests, agree on what each layer means in your project. Ambiguity here causes the most confusion.

| Layer        | Scope                                          | Dependencies                        | Speed Target   |
|--------------|-------------------------------------------------|-------------------------------------|----------------|
| Unit         | Single function or class, isolated              | None (all injected or mocked)       | < 1 ms each    |
| Integration  | Two or more real components working together    | Database, cache, local services     | < 5 s each     |
| E2E          | Full application stack, user-facing entry point | All services, possibly deployed     | < 60 s each    |

The key distinction: **unit tests replace all collaborators; integration tests use real collaborators for the boundary being tested.** A test that calls your service layer with a real database but a mocked HTTP client is an integration test for the database boundary and a unit test for the HTTP boundary. Be explicit about which boundary you are testing.

---

## Pytest Marker Strategy

Use pytest markers to separate test layers. This lets you run each layer independently and set different CI timeouts.

```python
# conftest.py at project root
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "unit: pure unit tests, no external deps")
    config.addinivalue_line("markers", "integration: requires running services")
    config.addinivalue_line("markers", "e2e: full stack, may require deployment")
    config.addinivalue_line("markers", "aws: requires AWS credentials or mocks")
```

```ini
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
markers =
    unit: pure unit tests
    integration: requires running services
    e2e: full stack tests
    aws: requires AWS credentials or mocks
```

Run selectively:

```bash
pytest -m unit                    # fast, no deps
pytest -m integration             # needs services up
pytest -m "not e2e"               # everything except e2e
pytest -m "integration and aws"   # only AWS integration tests
```

A common mistake is not enforcing markers. Add a CI step that fails if any test file under `tests/integration/` lacks the `@pytest.mark.integration` decorator.

---

## Fixture Strategy

Integration test fixtures are more complex than unit test fixtures because they manage stateful external resources. Three principles guide fixture design:

### 1. Scope fixtures to the narrowest necessary lifetime

```python
@pytest.fixture(scope="session")
def db_engine():
    """One database engine per test session. Expensive to create."""
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db_session(db_engine):
    """Fresh transaction per test. Rolled back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

Session-scoped fixtures create the resource once. Function-scoped fixtures ensure test isolation. The transaction rollback pattern is the most reliable way to isolate database tests without truncating tables.

### 2. Use factory fixtures for varied test data

```python
@pytest.fixture
def make_user(db_session):
    def _make_user(name="test", email=None):
        user = User(name=name, email=email or f"{name}@test.com")
        db_session.add(user)
        db_session.flush()
        return user
    return _make_user
```

Factory fixtures avoid the trap of a single shared fixture that every test modifies, which creates hidden coupling between tests.

### 3. Make cleanup deterministic, not implicit

Every fixture that creates external state must have explicit teardown. Relying on garbage collection or process exit for cleanup causes resource leaks in CI.

```python
@pytest.fixture
def s3_test_bucket(s3_client):
    bucket_name = f"test-{uuid.uuid4().hex[:8]}"
    s3_client.create_bucket(Bucket=bucket_name)
    yield bucket_name
    # Deterministic cleanup
    objects = s3_client.list_objects_v2(Bucket=bucket_name).get("Contents", [])
    if objects:
        s3_client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": [{"Key": o["Key"]} for o in objects]}
        )
    s3_client.delete_bucket(Bucket=bucket_name)
```

---

## Environment Management

Integration tests need configuration: database URLs, service endpoints, credentials. Handle this with a layered approach.

**Layer 1 — Defaults in conftest.py** for local development:

```python
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://test:test@localhost:5432/testdb"
)
```

**Layer 2 — `.env.test` file** checked into the repo with non-secret defaults:

```
TEST_DATABASE_URL=postgresql://test:test@localhost:5432/testdb
TEST_REDIS_URL=redis://localhost:6379/1
AWS_DEFAULT_REGION=us-east-1
```

**Layer 3 — CI environment variables** override everything for pipeline-specific config.

Use `pytest-dotenv` or a manual `load_dotenv` call in `conftest.py` to load the `.env.test` file. Never commit real credentials. Use placeholder values or mock endpoints.

---

## Containerized Dependencies

For databases, caches, and message queues, run real instances in containers rather than mocking the protocol. Mocking PostgreSQL at the wire level is fragile; running a real PostgreSQL container is cheap and catches real bugs.

### docker-compose for local development

```yaml
# docker-compose.test.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: testdb
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5432:5432"
    tmpfs: /var/lib/postgresql/data  # RAM-backed for speed

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

Using `tmpfs` for database storage makes tests significantly faster since nothing writes to disk.

### pytest-docker or testcontainers

For CI environments where you want the test suite to manage its own containers:

```python
import testcontainers.postgres

@pytest.fixture(scope="session")
def postgres_container():
    with testcontainers.postgres.PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()
```

Trade-off: `testcontainers` adds startup latency (2-5 seconds per container) but eliminates the need for a separate `docker-compose up` step. For fast local iteration, pre-started containers via docker-compose are better. For CI reproducibility, testcontainers win.

---

## AWS-Aware Testing Patterns

AWS services present a spectrum of testing options. Choose based on fidelity requirements.

| Approach             | Fidelity  | Speed    | Cost     | Best For                          |
|----------------------|-----------|----------|----------|-----------------------------------|
| moto (in-process)    | Medium    | Fast     | Free     | S3, DynamoDB, SQS, SNS, IAM      |
| LocalStack           | High      | Moderate | Free/Pro | Complex multi-service workflows   |
| Real AWS (dev acct)  | Perfect   | Slow     | $$       | Final validation before deploy    |

### moto for unit-boundary tests

moto patches `boto3` in-process and is fast enough for function-scoped fixtures:

```python
import boto3
from moto import mock_aws

@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        yield client
```

moto works well for testing your code's interaction with AWS APIs. It does not validate IAM policies, resource limits, or eventual consistency behavior.

### Real AWS for integration boundaries

When you need to test actual AWS behavior (IAM permission boundaries, cross-service event delivery, Lambda cold starts), use a dedicated test account with resource tagging and automated cleanup:

```python
@pytest.fixture(scope="session")
def aws_integration_session():
    """Only runs when AWS_INTEGRATION_TESTS=1 is set."""
    if not os.environ.get("AWS_INTEGRATION_TESTS"):
        pytest.skip("AWS integration tests disabled")
    session = boto3.Session()
    yield session
```

Gate real AWS tests behind an environment variable and a dedicated pytest marker so they never run accidentally.

> For patterns specific to moto-based AWS testing, see the companion article **testing-aws-services-with-moto**.

---

## CI Strategy

### Parallelization

Use `pytest-xdist` to run tests in parallel, but be aware of shared state:

```bash
pytest -m unit -n auto                    # safe, no shared state
pytest -m integration -n 4 --dist loadgroup  # group by resource
```

For integration tests with shared databases, use the `--dist loadgroup` strategy and assign tests to groups:

```python
@pytest.mark.xdist_group("database")
@pytest.mark.integration
def test_user_creation(db_session):
    ...
```

### Timeout enforcement

Set per-marker timeouts to catch hanging tests early:

```ini
[tool.pytest.ini_options]
timeout = 30
timeout_method = "signal"
```

### CI pipeline structure

Run test layers in order of speed and independence:

1. **Lint and type check** (seconds) -- fail fast on syntax errors
2. **Unit tests** (seconds) -- no external deps
3. **Integration tests** (minutes) -- containerized deps, moto
4. **E2E tests** (minutes) -- full stack, possibly real AWS

If unit tests fail, skip integration and e2e to save CI minutes.

---

## Flake Reduction

Flaky integration tests erode trust in the test suite. Common causes and fixes:

| Cause                          | Fix                                                       |
|--------------------------------|-----------------------------------------------------------|
| Port conflicts                 | Use dynamic ports; let the container pick                  |
| Database state leaking         | Use transaction rollback, not truncate                     |
| Timing-dependent assertions    | Retry with backoff or use polling helpers                  |
| DNS resolution in containers   | Use IP addresses or `host.docker.internal`                 |
| Shared mutable test data       | Factory fixtures, not shared fixtures                      |
| Order-dependent tests          | Run with `pytest-randomly` to detect hidden coupling       |

For async code, always set explicit timeouts on `await` calls in tests. A missing timeout on an async fixture can hang the entire CI run.

```python
async def test_message_processing(queue_client):
    await queue_client.send("test-message")
    result = await asyncio.wait_for(
        queue_client.receive(),
        timeout=5.0
    )
    assert result.body == "test-message"
```

---

## Directory Structure

Organize tests to mirror the layer strategy:

```
tests/
  conftest.py              # shared config, markers, base fixtures
  unit/
    conftest.py            # unit-specific fixtures (mocks)
    test_models.py
    test_services.py
  integration/
    conftest.py            # database, container fixtures
    test_repository.py
    test_api_endpoints.py
  e2e/
    conftest.py            # full-stack fixtures
    test_user_workflows.py
  factories.py             # shared factory functions
```

Each layer gets its own `conftest.py` so fixtures are scoped appropriately. Shared factories live in a common module imported by any layer.

---

## Common Mistakes

| Mistake                                          | Why It Hurts                                                    |
|--------------------------------------------------|-----------------------------------------------------------------|
| Mocking the thing you are testing                | Proves nothing; the mock passes, production breaks              |
| Session-scoped fixtures with mutable state       | Tests pass individually, fail together                          |
| No marker enforcement                            | Integration tests run in unit suite, slowing everything down    |
| Skipping cleanup in fixtures                     | Resource leaks accumulate; CI environment degrades              |
| Hard-coding `localhost` URLs                     | Breaks in CI where services run on different hosts              |
| Using `time.sleep()` for synchronization         | Slow and unreliable; use polling or event-based waits           |
| Testing AWS with real credentials in unit tests  | Slow, costly, and fails when credentials expire                 |
| Shared database across parallel test workers     | Race conditions and phantom failures                            |

---

## Trade-offs

**Mocking vs. real dependencies:** More mocking means faster tests but lower confidence. More real dependencies means slower tests but bugs caught earlier. The right balance depends on your deployment frequency -- if you deploy daily, lean toward real dependencies; if you deploy hourly, lean toward mocks with periodic real integration runs.

**Testcontainers vs. docker-compose:** Testcontainers are self-contained and reproducible but add startup latency. Docker-compose is faster for local development but requires a separate setup step. Many teams use docker-compose locally and testcontainers in CI.

**moto vs. LocalStack:** moto is faster and simpler for single-service tests. LocalStack provides higher fidelity for multi-service interactions (e.g., S3 event triggering Lambda). Use moto by default; upgrade to LocalStack when moto's approximations cause false positives.

**Parallel vs. sequential integration tests:** Parallel tests are faster but require strict resource isolation. If your integration tests share a database, you need either per-worker databases or careful transaction isolation. Start sequential; parallelize only when test suite duration becomes a bottleneck.

---

## Related Articles

- **[testing-aws-services-with-moto](../testing/testing-aws-services-with-moto.md)** — Detailed patterns for mocking AWS services with moto in pytest.
