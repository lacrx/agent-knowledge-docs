---
title: Python Project Scaffolding for AWS
topics:
  - project-structure
  - python
  - aws
  - scaffolding
  - web-applications
skills:
  - scaffold-python-project
  - scaffold-fastapi
  - create-python-dockerfile
summary: >
  How to structure Python applications targeting AWS deployments, covering src/ layout, configuration isolation, dependency management, and separation of app, data, and infrastructure concerns.
aliases:
  - python aws project layout
  - python project structure aws
  - fastapi project scaffolding
related:
  - nextjs-project-scaffolding-aws
last-updated: 2026-06-25
---

# Python Project Scaffolding for AWS

## Overview

A well-structured Python project saves time at every stage: local development, testing, code review, CI, and deployment. When the target is AWS (Fargate, Lambda, or a hybrid), the structure must also account for AWS-specific concerns like boto3 client lifecycle, environment-variable-driven configuration, and clean separation between application code and infrastructure definitions.

This article explains the reasoning behind standard project layout decisions for Python applications targeting AWS. It covers directory structure, package boundaries, configuration management, dependency separation, and common mistakes that create pain later. The focus is on trade-offs and rationale rather than exact commands.

> **Skill:** For step-by-step project creation, use the `scaffold-python-project` skill. For FastAPI application layer setup, use the `scaffold-fastapi` skill. For containerization, use the `create-python-dockerfile` skill.

---

## The src/ Layout

The most important structural decision is where production code lives. Two conventions dominate Python projects:

| Layout | Structure | Pros | Cons |
|--------|-----------|------|------|
| Flat | `myapp/`, `tests/` at repo root | Simple, fewer import issues | Test code can accidentally import from the wrong place |
| src/ | `src/myapp/` or `src/` as the package root | Clean separation, prevents accidental imports of uninstalled code | Slightly more configuration needed |

For AWS-targeted projects, the `src/` layout is strongly preferred. The reason is deployment context: when your code runs in a Docker container on Fargate or as a Lambda package, the import path must be predictable. A `src/` layout makes it obvious what gets packaged and what stays behind (tests, scripts, infrastructure code).

```
my-project/
  src/
    api/          # HTTP layer (FastAPI routes, middleware)
    data/         # Models, schemas, database access
    agent/        # LLM agent logic (if applicable)
    parsers/      # Data transformation and parsing
    search/       # Search and indexing logic
  tests/
  scripts/
  infra/          # Terraform, CloudFormation (kept separate)
```

Each subdirectory under `src/` is a Python package (with `__init__.py`). The subdirectories represent functional boundaries, not deployment units. A single Fargate task runs the whole `src/` tree; the boundaries exist for humans and tests.

### Mirror tests to src

The `tests/` directory should mirror the `src/` structure:

```
src/
  api/
    app.py
    routes/
      health.py
      items.py
  data/
    models.py
    repository.py
tests/
  api/
    test_app.py
    routes/
      test_health.py
      test_items.py
  data/
    test_models.py
    test_repository.py
```

This convention means you never have to search for a test file. The path `src/api/routes/items.py` maps to `tests/api/routes/test_items.py`. When the mirror drifts (and it will), test coverage gaps become invisible.

---

## Separating App, Data, and Infrastructure

Three categories of code exist in most AWS-deployed Python projects. Mixing them creates the most common structural problems.

### Application code (`src/`)

Everything that runs at request time: route handlers, service functions, data access, business logic. This is what gets packaged into your Docker image or Lambda zip.

### Infrastructure code (`infra/` or a separate repo)

Terraform modules, CloudFormation templates, CDK stacks, task definitions. This code provisions AWS resources but never runs alongside your application. Keeping it in the same repo is fine for small teams; larger organizations often use a dedicated infrastructure repo.

The key rule: **infrastructure code must never import from `src/`, and `src/` must never import from `infra/`.** If your Terraform needs to know your app's port number, pass it via a variable, not by importing a Python constant.

### Scripts (`scripts/`)

Bootstrap scripts, database migrations, one-off data fixes, CI helpers. These run at build time or operator time, not at request time. They may import from `src/` but should not be imported by `src/`.

```
my-project/
  src/                  # runs at request time
  tests/                # runs in CI
  scripts/              # runs at build/operator time
    bootstrap.sh
    migrate.py
    seed_data.py
  infra/                # runs at provision time
    main.tf
    variables.tf
    fargate.tf
```

---

## Configuration and Environment Variables

AWS-deployed applications get their configuration from environment variables: ECS task definitions inject them, Lambda configuration sets them, and Secrets Manager can populate them at startup. Your project structure must support this pattern cleanly.

### The layered approach

```
.env.example        # checked in, documents all variables with placeholders
.env                # git-ignored, local development values
.env.test           # git-ignored or checked in with non-secret test defaults
```

`.env.example` is documentation. It lists every environment variable the application expects, with `<value-placeholder>` for secrets and sensible defaults for non-secrets. This file is checked into version control.

### Required vs. optional variables

Distinguish between variables that must be present and those with safe defaults:

```python
# Required: fail fast at startup if missing
DATABASE_URL = os.environ["DATABASE_URL"]

# Optional: safe default for local development
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
APP_PORT = int(os.getenv("APP_PORT", "8080"))
```

Using `os.environ["KEY"]` for required variables causes a `KeyError` at startup rather than a confusing `None`-related error at request time. This is the correct behavior for Fargate deployments where missing configuration means the task definition is wrong.

### Config module pattern

Centralize configuration in a single module rather than scattering `os.environ` calls across the codebase:

```python
# src/config.py
import os

class Settings:
    AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
    S3_BUCKET: str = os.environ["S3_BUCKET"]
    APP_ENV: str = os.environ.get("APP_ENV", "development")
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info")

settings = Settings()
```

Other modules import `settings` rather than calling `os.environ` directly. This creates a single place to see all configuration, makes testing easier (you can monkeypatch `settings` attributes), and prevents typos in environment variable names from being scattered across files.

---

## Dependency Management

### Separate production and development dependencies

```
requirements.txt          # production: what goes in the Docker image
requirements-dev.txt      # development: testing, linting, local tools
```

`requirements-dev.txt` starts with `-r requirements.txt` to include production dependencies, then adds development-only packages. This separation matters for Docker image size and attack surface: your Fargate container should not include `pytest`, `ruff`, or `moto`.

### Pin with ranges, not exact versions

```text
fastapi>=0.115.0,<1.0
uvicorn>=0.32.0,<1.0
boto3>=1.35.0,<2.0
```

Exact pins (`==1.2.3`) cause dependency conflicts in projects with multiple packages. Range pins allow patch updates while preventing breaking changes. For reproducible builds, use `pip freeze > requirements.lock` and install from the lock file in CI and Docker builds.

### Dependency boundaries

Keep your dependency tree shallow. A common mistake is importing a heavy library (pandas, scipy) for a single utility function that could be written in 10 lines of standard library code. Every dependency you add:

- Increases Docker image size (matters for Fargate cold starts and Lambda package limits)
- Adds a security surface
- Creates potential version conflicts

Before adding a dependency, ask: does this library provide enough value to justify its weight? For AWS-specific code, `boto3` is unavoidable, but many wrapper libraries around boto3 add complexity without proportional value.

---

## boto3 Client Management

boto3 clients are the primary interface to AWS services. How you create and manage them affects testability, performance, and configuration isolation.

### Lazy initialization

Never create boto3 clients at module import time:

```python
# Wrong: creates client when module is imported
s3_client = boto3.client("s3")  # fails if no credentials available

# Right: creates client on first use
_s3_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    return _s3_client
```

Module-level client creation breaks test imports (credentials may not exist in CI) and makes it impossible to mock the client before it is created.

### Client boundaries

Group AWS interactions behind a boundary layer. Rather than calling `boto3` directly from route handlers or service functions, create wrapper modules:

```python
# src/data/storage.py
from src.api.clients import get_s3_client

def upload_file(bucket: str, key: str, body: bytes) -> str:
    client = get_s3_client()
    client.put_object(Bucket=bucket, Key=key, Body=body)
    return f"s3://{bucket}/{key}"
```

This boundary makes testing straightforward: mock `get_s3_client` to return a fake, or use moto to patch the entire boto3 layer. It also centralizes retry logic and error handling for each AWS service.

### Region and endpoint configuration

Always pass `region_name` explicitly rather than relying on the default credential chain's region resolution. In Fargate, the task role provides credentials, but the region must still be configured. Make it explicit:

```python
boto3.client("s3", region_name=settings.AWS_REGION)
```

For local development against LocalStack or moto, support an endpoint override:

```python
kwargs = {"region_name": settings.AWS_REGION}
if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
    kwargs["endpoint_url"] = endpoint
client = boto3.client("s3", **kwargs)
```

---

## FastAPI Service Organization

FastAPI projects benefit from a specific organizational pattern that keeps the entry point thin and routes modular.

### Entry point (`src/api/app.py`)

The `app.py` file should contain only wiring: creating the FastAPI instance, mounting static files, and registering routers. No business logic, no database queries, no AWS calls.

```python
app = FastAPI(title=settings.APP_TITLE, version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(items_router, prefix="/api/v1/items")
app.include_router(web_router)  # catch-all last
```

### Router files (`src/api/routes/`)

Each feature gets its own router file. Routers handle HTTP concerns (request parsing, response formatting, status codes) and delegate to service functions for business logic.

### Service layer (`src/` domain packages)

Business logic lives in domain packages (`src/data/`, `src/agent/`, etc.), not in route handlers. This separation means your business logic can be tested without HTTP, reused across routes, and called from scripts or background tasks.

### Lifespan management

Use FastAPI's lifespan context manager for startup and shutdown tasks (database connection pools, cache warming, background task cleanup). This replaces the deprecated `on_startup`/`on_shutdown` events and integrates cleanly with async resource management.

---

## Deployment Readiness

Structuring your project for AWS deployment from the start avoids painful restructuring later.

### Fargate considerations

- **Port convention:** Use port 8080 consistently. Match it in your Dockerfile `EXPOSE`, uvicorn startup, and ECS task definition `containerPort`.
- **Single worker:** Run uvicorn with `--workers 1` when using in-memory state. Fargate scales horizontally via task count, not via workers within a single task.
- **Health check endpoint:** Always provide a `/health` endpoint that returns 200 with no external dependencies. The ALB uses this to determine task health. If your health check queries a database and the database is slow, the ALB will kill healthy tasks.
- **Graceful shutdown:** Handle `SIGTERM` properly. Fargate sends `SIGTERM` before stopping a task. Uvicorn handles this by default, but custom background tasks need explicit signal handling.

### Lambda considerations

- **Package size:** Keep the deployment package under 50 MB (250 MB unzipped). This is another reason to avoid heavy dependencies.
- **Handler location:** Lambda expects a handler function at a specific path (e.g., `src.api.handler.lambda_handler`). The `src/` layout works well here because the import path is clear.
- **Cold start awareness:** Import-time side effects (boto3 client creation, database connections) slow cold starts. Lazy initialization helps.

### Docker structure

The Dockerfile should install only production dependencies, copy only `src/`, and set a non-root user:

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
USER appuser
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

Do not copy `tests/`, `scripts/`, `infra/`, or development configuration into the production image. The `src/` layout makes this copy step clean and obvious.

---

## Bootstrap Conventions

Every project should include a `bootstrap.sh` (or equivalent) that takes a fresh clone to a working state in one command:

```bash
./bootstrap.sh
```

The script should:

1. Check Python version (fail fast if wrong)
2. Create a virtual environment
3. Install development dependencies
4. Run linting
5. Run tests

If any step fails, the script exits with a non-zero code. New team members should be able to clone the repo and run `bootstrap.sh` with no other setup. This also serves as documentation for CI: the CI pipeline should run the same steps as the bootstrap script.

---

## Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Mixing infra code in `src/` | Terraform imports Python modules; changes to app code break provisioning | Keep `infra/` completely separate; no cross-imports |
| Hard-coded AWS region or account ID | Breaks in different environments; credentials leak in code review | Use environment variables for all AWS-specific values |
| `os.environ` calls scattered across files | Configuration is invisible; typos cause runtime errors | Centralize in a `config.py` module |
| One `requirements.txt` for everything | Production image includes pytest, ruff, moto; larger attack surface | Split into `requirements.txt` and `requirements-dev.txt` |
| boto3 clients created at import time | Tests fail on import; no opportunity to mock before client exists | Use lazy initialization with getter functions |
| Tests not mirroring `src/` structure | Can't find test files; coverage gaps go unnoticed | Enforce 1:1 directory mapping |
| Business logic in route handlers | Can't test without HTTP; can't reuse in scripts or background tasks | Extract to service functions in domain packages |
| No bootstrap script | New contributors spend hours on setup; CI diverges from local dev | Create `bootstrap.sh` that takes a fresh clone to passing tests |
| `.env` file checked into git | Secrets exposed in version control | Add `.env` to `.gitignore`; check in `.env.example` only |
| Flat test directory with no markers | Integration tests run in unit suite; CI is slow and flaky | Mirror `src/` structure; use pytest markers to separate layers |

---

## Trade-offs

**src/ layout vs. flat layout:** The `src/` layout adds a directory level and requires slightly more import path configuration. The payoff is unambiguous packaging: everything under `src/` goes into the container, nothing else does. For projects with multiple deployment targets (Fargate and Lambda), this clarity is worth the extra nesting.

**Single config module vs. distributed config:** Centralizing configuration in `config.py` means every developer knows where to look, but it also means that module must be imported early and its failure modes affect the entire application. For small projects this is the right trade-off. For large projects with many independent services in one repo, consider per-service config modules.

**Wrapper modules vs. direct boto3 calls:** Wrapping every AWS call adds boilerplate. Direct boto3 calls are faster to write. The wrapper pays for itself when you need to add retries, switch to a mock for testing, or change the underlying AWS service (e.g., moving from S3 to EFS). For projects with only 2-3 AWS calls, wrappers are optional. For projects with 10+, they are essential.

**Monorepo vs. separate repos:** Keeping infrastructure code alongside application code in one repo simplifies deployment pipelines and ensures version alignment. Separate repos give infrastructure its own review process and access controls. Teams with dedicated platform engineers tend toward separate repos; small teams doing everything tend toward monorepos.

**Range pins vs. exact pins:** Range pins allow flexibility but can cause "works on my machine" issues when different developers resolve different versions. Exact pins guarantee reproducibility but create merge conflicts and make upgrades tedious. The best compromise is range pins in `requirements.txt` with a `requirements.lock` generated by `pip freeze` for reproducible builds.
