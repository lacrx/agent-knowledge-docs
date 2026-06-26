---
name: setup-python-aws-tests
title: Set Up Python AWS Test Infrastructure
type: skill
topics:
  - python
  - testing
  - aws
  - pytest
  - moto
  - fastapi
summary: >
  Set up pytest infrastructure for Python apps that use AWS services with
  moto-based mocks, shared fixtures, test data patterns, FastAPI test examples,
  and repeatable commands for local and CI test runs.
references:
  - skills/scaffold-python-project.md
  - skills/setup-python-integration-tests.md
  - articles/testing/testing-aws-services-with-moto.md
last-updated: 2026-06-25
---

# Set Up Python AWS Test Infrastructure

Create a pytest test suite for Python applications that call AWS services.
Uses moto for deterministic, offline AWS mocks. Follow steps in order.

---

## Prerequisites

- Python >= 3.11
- A Python project with `pyproject.toml` or `requirements.txt`
- Application code that uses boto3 to interact with AWS services
- No real AWS credentials required (tests use fake credentials)

---

## Steps

### Step 1: Install test dependencies

```bash
pip install pytest pytest-asyncio pytest-cov "moto[s3,dynamodb,sqs,secretsmanager]" httpx boto3

# If using pyproject.toml, add to dev dependencies:
cat >> pyproject.toml << 'PYPROJECT'

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "moto[s3,dynamodb,sqs,secretsmanager]>=5.0",
    "httpx>=0.27",
]
PYPROJECT
```

### Step 2: Create test directory layout and env file

```bash
TEST_DIR="${test_directory:-tests}"
mkdir -p "$TEST_DIR"/{unit,integration,fixtures,data}
touch "$TEST_DIR"/__init__.py "$TEST_DIR"/unit/__init__.py \
      "$TEST_DIR"/integration/__init__.py "$TEST_DIR"/fixtures/__init__.py

ENV_FILE="${env_file_path:-.env.test}"
cat > "$ENV_FILE" << 'ENVFILE'
AWS_ACCESS_KEY_ID=testing
AWS_SECRET_ACCESS_KEY=testing
AWS_SECURITY_TOKEN=testing
AWS_SESSION_TOKEN=testing
AWS_DEFAULT_REGION=${aws_region:-us-east-1}
AWS_REGION=${aws_region:-us-east-1}
ENVFILE
```

### Step 3: Configure pytest in pyproject.toml

```bash
cat >> pyproject.toml << 'PYPROJECT'

[tool.pytest.ini_options]
testpaths = ["${test_directory:-tests}"]
asyncio_mode = "auto"
markers = [
    "unit: fast isolated tests (no external deps)",
    "integration: tests requiring mocked AWS services",
]
addopts = "${pytest_addopts:--v --tb=short}"
timeout = ${timeout_seconds:-30}
filterwarnings = ["ignore::DeprecationWarning:moto.*"]

[tool.coverage.run]
source = ["src"]
omit = ["${test_directory:-tests}/*"]

[tool.coverage.report]
fail_under = ${coverage_target:-80}
show_missing = true
exclude_lines = ["pragma: no cover", "if __name__ == .__main__.", "if TYPE_CHECKING:"]
PYPROJECT
```

### Step 4: Create root conftest with shared AWS fixtures

```bash
TEST_DIR="${test_directory:-tests}"
cat > "$TEST_DIR/conftest.py" << 'CONFTEST'
"""Shared fixtures: fake AWS credentials and moto-based service mocks."""

import os
import pytest
import boto3
from moto import mock_aws

REGION = os.getenv("AWS_REGION", "us-east-1")

@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch):
    """Override AWS credentials so no real calls can escape."""
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

@pytest.fixture
def s3_client():
    with mock_aws():
        yield boto3.client("s3", region_name=REGION)

@pytest.fixture
def s3_bucket(s3_client):
    name = "test-bucket"
    s3_client.create_bucket(
        Bucket=name,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )
    return name

@pytest.fixture
def dynamodb_resource():
    with mock_aws():
        yield boto3.resource("dynamodb", region_name=REGION)

@pytest.fixture
def dynamodb_table(dynamodb_resource):
    table = dynamodb_resource.create_table(
        TableName="test-table",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    return table

@pytest.fixture
def sqs_client():
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION)

@pytest.fixture
def sqs_queue_url(sqs_client):
    return sqs_client.create_queue(QueueName="test-queue")["QueueUrl"]

@pytest.fixture
def secrets_client():
    with mock_aws():
        yield boto3.client("secretsmanager", region_name=REGION)

@pytest.fixture
def test_secret(secrets_client):
    name = "test/api-key"
    secrets_client.create_secret(
        Name=name, SecretString='{"api_key": "fake-key-for-testing"}',
    )
    return name
CONFTEST
```

### Step 5: Create sample unit tests for S3

```bash
TEST_DIR="${test_directory:-tests}"
cat > "$TEST_DIR/unit/test_s3_service.py" << 'UNITTEST'
"""Unit tests for S3 interactions."""
from moto import mock_aws

@mock_aws
class TestS3Operations:
    def test_put_and_get_object(self, s3_client, s3_bucket):
        s3_client.put_object(Bucket=s3_bucket, Key="doc.json", Body=b'{"ok":true}')
        resp = s3_client.get_object(Bucket=s3_bucket, Key="doc.json")
        assert resp["Body"].read() == b'{"ok":true}'

    def test_list_objects_empty_bucket(self, s3_client, s3_bucket):
        assert s3_client.list_objects_v2(Bucket=s3_bucket)["KeyCount"] == 0

    def test_delete_object(self, s3_client, s3_bucket):
        s3_client.put_object(Bucket=s3_bucket, Key="tmp.txt", Body=b"x")
        s3_client.delete_object(Bucket=s3_bucket, Key="tmp.txt")
        assert s3_client.list_objects_v2(Bucket=s3_bucket, Prefix="tmp.txt")["KeyCount"] == 0
UNITTEST
```

### Step 6: Create sample unit tests for DynamoDB

```bash
TEST_DIR="${test_directory:-tests}"
cat > "$TEST_DIR/unit/test_dynamodb_service.py" << 'UNITTEST'
"""Unit tests for DynamoDB interactions."""
from moto import mock_aws

@mock_aws
class TestDynamoDBOperations:
    def test_put_and_get_item(self, dynamodb_table):
        dynamodb_table.put_item(Item={"pk": "user-1", "name": "Alice"})
        assert dynamodb_table.get_item(Key={"pk": "user-1"})["Item"]["name"] == "Alice"

    def test_get_missing_item(self, dynamodb_table):
        assert "Item" not in dynamodb_table.get_item(Key={"pk": "nonexistent"})

    def test_delete_item(self, dynamodb_table):
        dynamodb_table.put_item(Item={"pk": "user-2", "name": "Bob"})
        dynamodb_table.delete_item(Key={"pk": "user-2"})
        assert "Item" not in dynamodb_table.get_item(Key={"pk": "user-2"})
UNITTEST
```

### Step 7: Create integration tests for SQS and Secrets Manager

```bash
TEST_DIR="${test_directory:-tests}"
cat > "$TEST_DIR/integration/test_sqs_secrets.py" << 'UNITTEST'
"""Integration tests for SQS and Secrets Manager."""
import json
from moto import mock_aws

@mock_aws
class TestSQSOperations:
    def test_send_and_receive_message(self, sqs_client, sqs_queue_url):
        body = json.dumps({"event": "order.created", "order_id": "123"})
        sqs_client.send_message(QueueUrl=sqs_queue_url, MessageBody=body)
        msgs = sqs_client.receive_message(QueueUrl=sqs_queue_url, MaxNumberOfMessages=1)["Messages"]
        assert len(msgs) == 1
        assert json.loads(msgs[0]["Body"])["order_id"] == "123"

@mock_aws
class TestSecretsManagerOperations:
    def test_get_secret_value(self, secrets_client, test_secret):
        resp = secrets_client.get_secret_value(SecretId=test_secret)
        assert json.loads(resp["SecretString"])["api_key"] == "fake-key-for-testing"
UNITTEST
```

### Step 8: Create FastAPI test example with mocked AWS backend

```bash
TEST_DIR="${test_directory:-tests}"
cat > "$TEST_DIR/integration/test_api.py" << 'APITEST'
"""FastAPI test example with mocked AWS services.

Uncomment the TestAPIWithAWS class and adjust imports to match your app.
"""
# from src.app.main import app
# from httpx import ASGITransport, AsyncClient
# from moto import mock_aws
# import pytest
#
# @pytest.mark.integration
# class TestAPIWithAWS:
#     @pytest.fixture
#     def client(self):
#         transport = ASGITransport(app=app)
#         return AsyncClient(transport=transport, base_url="http://test")
#
#     @mock_aws
#     async def test_create_item(self, client, dynamodb_table):
#         resp = await client.post("/items", json={"id": "item-1", "name": "Widget"})
#         assert resp.status_code == 201
#         assert dynamodb_table.get_item(Key={"pk": "item-1"})["Item"]["name"] == "Widget"

class TestFixtureWiring:
    """Verify all fixtures are available and wired correctly."""
    def test_s3_fixture(self, s3_client, s3_bucket):
        names = [b["Name"] for b in s3_client.list_buckets()["Buckets"]]
        assert s3_bucket in names

    def test_dynamodb_fixture(self, dynamodb_table):
        assert dynamodb_table.table_status == "ACTIVE"

    def test_sqs_fixture(self, sqs_client, sqs_queue_url):
        assert "test-queue" in sqs_queue_url

    def test_secrets_fixture(self, secrets_client, test_secret):
        assert secrets_client.get_secret_value(SecretId=test_secret)["Name"] == test_secret
APITEST
```

### Step 9: Add test data factories

```bash
TEST_DIR="${test_directory:-tests}"
cat > "$TEST_DIR/fixtures/factories.py" << 'FACTORIES'
"""Test data factories for building consistent test objects."""

def make_item(pk: str = "test-pk", **overrides) -> dict:
    item = {"pk": pk, "status": "active", "version": 1}
    item.update(overrides)
    return item

def make_sqs_message(event_type: str = "test.event", **payload) -> dict:
    msg = {"event": event_type, "version": "1.0"}
    msg.update(payload)
    return msg
FACTORIES
```

### Step 10: Run tests locally

```bash
ENV_FILE="${env_file_path:-.env.test}"
set -a && source "$ENV_FILE" && set +a

# Full suite with coverage
pytest "${test_directory:-tests}" \
  --cov=src --cov-report=term-missing --cov-report=html:htmlcov -v --tb=short

# Unit tests only
pytest "${test_directory:-tests}/unit" -m unit -v

# Integration tests only
pytest "${test_directory:-tests}/integration" -m integration -v
```

### Step 11: Add CI workflow

```bash
mkdir -p .github/workflows
cat > .github/workflows/test.yml << 'WORKFLOW'
name: Tests
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
env:
  AWS_ACCESS_KEY_ID: testing
  AWS_SECRET_ACCESS_KEY: testing
  AWS_SECURITY_TOKEN: testing
  AWS_SESSION_TOKEN: testing
  AWS_DEFAULT_REGION: ${aws_region:-us-east-1}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - name: Unit tests
        run: pytest ${test_directory:-tests}/unit -v --tb=short
      - name: Integration tests
        run: pytest ${test_directory:-tests}/integration -v --tb=short
      - name: Coverage
        run: |
          pytest ${test_directory:-tests} \
            --cov=src --cov-report=xml:coverage.xml \
            --cov-fail-under=${coverage_target:-80}
WORKFLOW
```

### Step 12: Update .gitignore and verify

```bash
cat >> .gitignore << 'GITIGNORE'

# Test artifacts
htmlcov/
.coverage
coverage.xml
.pytest_cache/
GITIGNORE

# Verify tests pass
ENV_FILE="${env_file_path:-.env.test}"
set -a && source "$ENV_FILE" && set +a
pytest "${test_directory:-tests}" -v --tb=short
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use pytest, pytest-asyncio, pytest-cov, and moto only | Standardized stack; moto provides offline AWS mocks without custom fakes |
| No real AWS credentials or network calls | Fake credentials in fixtures and env file; moto intercepts all boto3 calls |
| Separate `unit/` and `integration/` directories | Clear categorization; CI can run them independently |
| No secrets in committed config files | `.env.test` contains only fake `testing` values; real credentials stay in vaults |
| `autouse=True` on credential fixture | Guarantees every test gets fake credentials even if a fixture is forgotten |
| Each service fixture uses its own `mock_aws` context | Isolates service state between tests; prevents cross-test leakage |
| Deterministic test data via factory functions | Avoids random data that makes failures hard to reproduce |
| Coverage target enforced via `fail_under` | Prevents coverage regression; configurable per project |
| Timeout per test | Prevents hanging tests from blocking CI; default 30 seconds |

---

## Outputs

- Test directory layout: `tests/unit/`, `tests/integration/`, `tests/fixtures/`, `tests/data/`
- Root `conftest.py` with shared fixtures for S3, DynamoDB, SQS, and Secrets Manager
- Sample unit tests for S3 and DynamoDB operations
- Sample integration tests for SQS and Secrets Manager
- FastAPI test scaffold with commented async client example
- Test data factory module with reusable builders
- `pytest` configuration in `pyproject.toml` with markers, coverage, and timeout
- Fake credentials environment file (`.env.test`)
- CI workflow for GitHub Actions with unit, integration, and coverage stages
- Local run command: `pytest tests --cov=src --cov-report=term-missing -v`
- CI run command: `pytest tests --cov=src --cov-report=xml --cov-fail-under=80`
