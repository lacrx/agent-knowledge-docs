---
name: setup-python-integration-tests
title: Set Up Python Integration Tests
type: skill
topics:
  - python
  - testing
  - pytest
  - integration-tests
  - docker
  - ci
summary: >
  Set up pytest-based integration test infrastructure with markers, fixtures,
  service/database/container-backed test patterns, and commands for local and CI execution.
references:
  - skills/scaffold-python-project.md
  - skills/setup-python-aws-tests.md
  - articles/testing/python-integration-testing-patterns.md
last-updated: 2026-06-25
---

# Set Up Python Integration Tests

Create a pytest integration test layout with custom markers, reusable fixtures
for database and service backends, Docker Compose support, and commands for
running tests locally and in CI. Follow steps in order.

---

## Prerequisites

- Python >= 3.10
- `pip` or `uv` available for package installation
- Docker and Docker Compose installed (for container-backed tests)
- Project repository initialized with a `src/` or flat package layout
- `.env.example` file with placeholder values (no real secrets)

---

## Steps

### Step 1: Define variables

Create or update `pyproject.toml` with test configuration. Replace placeholder
values in angle brackets with project-specific values.

```toml
# pyproject.toml — test-related sections only

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-timeout>=2.3",
    "pytest-env>=1.1",
    "httpx>=0.27",
    "sqlalchemy>=2.0",
    "psycopg2-binary>=2.9",
]

[tool.pytest.ini_options]
testpaths = ["<test_directory>"]
markers = [
    "<integration_marker_name>: marks tests that require external services (deselect with '-m \"not <integration_marker_name>\"')",
    "database: marks tests that require a running database",
    "api: marks tests that hit a live API endpoint",
]
addopts = "<pytest_addopts>"
timeout = "<timeout_seconds>"
env = [
    "TEST_DATABASE_URL=<test_database_url>",
    "AWS_REGION=<aws_region>",
    "AWS_DEFAULT_REGION=<aws_region>",
    "SERVICE_ENDPOINT_URL=<service_endpoint_url>",
]
```

### Step 2: Create test directory structure

```bash
TEST_DIR="<test_directory>"
MARKER="<integration_marker_name>"

mkdir -p "${TEST_DIR}/unit"
mkdir -p "${TEST_DIR}/${MARKER}"
mkdir -p "${TEST_DIR}/${MARKER}/api"
mkdir -p "${TEST_DIR}/${MARKER}/database"
touch "${TEST_DIR}/__init__.py"
touch "${TEST_DIR}/unit/__init__.py"
touch "${TEST_DIR}/${MARKER}/__init__.py"
touch "${TEST_DIR}/${MARKER}/api/__init__.py"
touch "${TEST_DIR}/${MARKER}/database/__init__.py"
```

### Step 3: Create the root conftest with shared fixtures

```python
# <test_directory>/conftest.py
"""Root conftest — shared fixtures available to all tests."""

import os

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "<integration_marker_name>: marks tests requiring external services",
    )
    config.addinivalue_line(
        "markers",
        "database: marks tests requiring a running database",
    )
    config.addinivalue_line(
        "markers",
        "api: marks tests hitting a live API endpoint",
    )


@pytest.fixture(scope="session")
def env_config():
    """Load environment configuration for the test session."""
    return {
        "database_url": os.getenv(
            "TEST_DATABASE_URL", "<test_database_url>"
        ),
        "aws_region": os.getenv("AWS_REGION", "<aws_region>"),
        "service_endpoint_url": os.getenv(
            "SERVICE_ENDPOINT_URL", "<service_endpoint_url>"
        ),
    }
```

### Step 4: Create the integration conftest with service fixtures

```python
# <test_directory>/<integration_marker_name>/conftest.py
"""Integration conftest — fixtures for service-backed tests."""

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def database_url():
    """Return the test database URL from the environment."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — skipping database tests")
    return url


@pytest.fixture(scope="session")
def db_engine(database_url):
    """Create a SQLAlchemy engine scoped to the test session."""
    from sqlalchemy import create_engine

    engine = create_engine(database_url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Provide a transactional database session that rolls back after each test."""
    from sqlalchemy.orm import Session

    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="session")
def api_client():
    """Create an httpx client pointed at the service endpoint."""
    import httpx

    base_url = os.getenv(
        "SERVICE_ENDPOINT_URL", "<service_endpoint_url>"
    )
    with httpx.Client(base_url=base_url, timeout=<timeout_seconds>) as client:
        yield client
```

### Step 5: Create the env file template

```bash
# .env.example — committed to the repo; real values stay out of version control
cat > .env.example << 'ENVEOF'
# Integration test environment variables
TEST_DATABASE_URL=<test_database_url>
AWS_REGION=<aws_region>
AWS_DEFAULT_REGION=<aws_region>
SERVICE_ENDPOINT_URL=<service_endpoint_url>
ENVEOF
```

### Step 6: Create the Docker Compose file for local services

```yaml
# <docker_compose_file>
services:
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: test_db
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test"]
      interval: 5s
      timeout: 3s
      retries: 5

  localstack:
    image: localstack/localstack:3
    ports:
      - "4566:4566"
    environment:
      SERVICES: s3,sqs,sns,dynamodb,secretsmanager
      AWS_DEFAULT_REGION: "<aws_region>"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 3s
      retries: 5
```

### Step 7: Write an example API integration test

```python
# <test_directory>/<integration_marker_name>/api/test_health.py
"""Example API integration test."""

import pytest


@pytest.mark.<integration_marker_name>
@pytest.mark.api
class TestHealthEndpoint:
    """Verify the service health endpoint responds correctly."""

    def test_health_returns_200(self, api_client):
        response = api_client.get("/health")
        assert response.status_code == 200

    def test_health_body_contains_status(self, api_client):
        response = api_client.get("/health")
        body = response.json()
        assert "status" in body
        assert body["status"] == "ok"
```

### Step 8: Write an example database integration test

```python
# <test_directory>/<integration_marker_name>/database/test_user_repo.py
"""Example database integration test."""

import pytest
from sqlalchemy import text


@pytest.mark.<integration_marker_name>
@pytest.mark.database
class TestUserRepository:
    """Verify database operations against a real Postgres instance."""

    def test_insert_and_select_user(self, db_session):
        db_session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS users "
                "(id SERIAL PRIMARY KEY, name VARCHAR(100))"
            )
        )
        db_session.execute(
            text("INSERT INTO users (name) VALUES (:name)"),
            {"name": "alice"},
        )
        result = db_session.execute(text("SELECT name FROM users")).fetchone()
        assert result[0] == "alice"

    def test_transaction_isolation(self, db_session):
        """Each test gets a fresh transaction — previous inserts are rolled back."""
        db_session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS users "
                "(id SERIAL PRIMARY KEY, name VARCHAR(100))"
            )
        )
        result = db_session.execute(
            text("SELECT count(*) FROM users")
        ).fetchone()
        assert result[0] == 0
```

### Step 9: Add a pytest marker helper for skipping in CI

```python
# <test_directory>/helpers.py
"""Shared test helpers."""

import os

import pytest

requires_docker = pytest.mark.skipif(
    os.getenv("CI") == "true" and os.getenv("DOCKER_AVAILABLE") != "true",
    reason="Docker not available in this CI environment",
)
```

### Step 10: Create the local test runner script

```bash
cat > run_integration_tests.sh << 'RUNEOF'
#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="<docker_compose_file>"
ENV_FILE="<env_file_path>"
TEST_DIR="<test_directory>"
MARKER="<integration_marker_name>"
COVERAGE_TARGET="<coverage_target>"

echo "--- Starting test services ---"
docker compose -f "${COMPOSE_FILE}" up -d --wait

echo "--- Running integration tests ---"
set +e
pytest \
  "${TEST_DIR}/${MARKER}" \
  -m "${MARKER}" \
  --timeout="<timeout_seconds>" \
  --cov=src \
  --cov-report=term-missing \
  --cov-report=html:htmlcov \
  --cov-fail-under="${COVERAGE_TARGET}" \
  -v
TEST_EXIT=$?
set -e

echo "--- Tearing down test services ---"
docker compose -f "${COMPOSE_FILE}" down -v

exit ${TEST_EXIT}
RUNEOF
chmod +x run_integration_tests.sh
```

### Step 11: Create the CI workflow step

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
env:
  TEST_DATABASE_URL: "<test_database_url>"
  AWS_REGION: "<aws_region>"
  SERVICE_ENDPOINT_URL: "<service_endpoint_url>"
jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: --health-cmd "pg_isready -U test" --health-interval 5s --health-timeout 3s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[test]"
      - name: Run unit tests
        run: pytest <test_directory>/unit -v
      - name: Run integration tests
        run: |
          pytest <test_directory>/<integration_marker_name> \
            -m "<integration_marker_name>" --timeout=<timeout_seconds> \
            --cov=src --cov-report=term-missing \
            --cov-report=xml:coverage.xml \
            --cov-fail-under=<coverage_target> -v
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-report
          path: coverage.xml
```

### Step 12: Verify the setup

```bash
# Install test dependencies
pip install -e ".[test]"

# Run only unit tests (quick sanity check)
pytest <test_directory>/unit -v

# Run only integration tests with marker
pytest -m "<integration_marker_name>" -v --timeout=<timeout_seconds>

# Run all tests with coverage
pytest <test_directory> \
  --cov=src \
  --cov-report=term-missing \
  --cov-fail-under=<coverage_target> \
  -v
```

### Step 13: Commit and PR

```bash
git add \
  pyproject.toml \
  <test_directory>/ \
  .env.example \
  <docker_compose_file> \
  run_integration_tests.sh \
  .github/workflows/integration-tests.yml

git commit -m "Add pytest integration test infrastructure"
gh pr create \
  --title "Set up Python integration tests" \
  --body "Adds integration test layout, fixtures, Docker Compose services, example tests, and CI workflow"
```

---

## Examples

### Run database tests locally

```bash
docker compose -f <docker_compose_file> up -d postgres --wait
pytest -m "database" -v --timeout=<timeout_seconds>
docker compose -f <docker_compose_file> down -v
```

### Run API tests against a staging endpoint

```bash
SERVICE_ENDPOINT_URL=https://staging.example.com pytest -m "api" -v --timeout=<timeout_seconds>
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use pytest as the test runner | Standard, extensible, wide ecosystem of plugins |
| Separate integration tests from unit tests in directory structure | Unit tests run fast without services; integration tests require setup |
| Use `@pytest.mark.<integration_marker_name>` on all integration tests | Allows selective execution via `-m` flag in local and CI runs |
| No secrets in committed config files | Use `.env.example` with placeholders; real values come from environment or CI secrets |
| Database fixtures use transaction rollback | Each test gets a clean state without expensive table drops or re-seeding |
| Session-scoped engine, function-scoped session | Engine creation is expensive; per-test sessions ensure isolation |
| Docker Compose healthchecks on all services | Prevents tests from starting before services are ready |
| Timeout enforced on every test via `--timeout` | Prevents hung connections from blocking CI indefinitely |
| Coverage target enforced with `--cov-fail-under` | Prevents coverage regression on integration-tested code paths |
| `docker compose down -v` after test runs | Removes volumes to prevent state leaking between runs |

---

## Outputs

- Test directory layout with separate `unit/` and `<integration_marker_name>/` subdirectories
- Root `conftest.py` with marker registration and session-scoped env config fixture
- Integration `conftest.py` with database engine, transactional session, and API client fixtures
- Example API integration test and database integration test files
- `.env.example` with placeholder environment variables
- Docker Compose file with Postgres and LocalStack services
- Local runner script (`run_integration_tests.sh`) with service lifecycle management
- CI workflow (`.github/workflows/integration-tests.yml`) with GitHub Actions service containers
- Pytest command: `pytest -m "<integration_marker_name>" -v --timeout=<timeout_seconds>`
- Coverage command: `pytest --cov=src --cov-report=term-missing --cov-fail-under=<coverage_target>`
