---
name: scaffold-python-project
title: Scaffold Python Project
type: skill
topics:
  - python
  - scaffolding
  - project-setup
  - fastapi
  - aws
summary: >
  Scaffold a Python 3.12+ FastAPI project from scratch with src/ layout, tests mirroring
  src, venv-based dependency management, bootstrap script, and AWS-ready configuration.
references:
  - skills/create-python-dockerfile.md
  - skills/scaffold-fastapi.md
last-updated: 2026-06-13
---

# Scaffold Python Project

Create a complete Python project structure for a FastAPI app deployed to AWS Fargate.
Follow steps in order.

---

## Prerequisites

- Python 3.12+ installed
- `pip` and `venv` available (standard library)
- Git installed

---

## Steps

### Step 1: Create directory structure

```bash
PROJECT="my-project"

mkdir -p ${PROJECT}/src/{api,data,agent,parsers,search}
mkdir -p ${PROJECT}/tests/{api,data,agent,parsers,search}
mkdir -p ${PROJECT}/scripts
mkdir -p ${PROJECT}/.github/workflows
```

### Step 2: Create `__init__.py` in every package directory

```bash
cd ${PROJECT}

touch src/__init__.py
touch src/api/__init__.py
touch src/data/__init__.py
touch src/agent/__init__.py
touch src/parsers/__init__.py
touch src/search/__init__.py

touch tests/__init__.py
touch tests/api/__init__.py
touch tests/data/__init__.py
touch tests/agent/__init__.py
touch tests/parsers/__init__.py
touch tests/search/__init__.py
```

### Step 3: Create `requirements.txt`

```text
fastapi>=0.115.0,<1.0
uvicorn>=0.32.0,<1.0
pydantic>=2.10.0,<3.0
python-dotenv>=1.0.0,<2.0
boto3>=1.35.0,<2.0
httpx>=0.28.0,<1.0
```

### Step 4: Create `requirements-dev.txt`

```text
-r requirements.txt
pytest>=8.3.0,<9.0
pytest-cov>=6.0.0,<7.0
pytest-asyncio>=0.24.0,<1.0
moto[all]>=5.0.0,<6.0
ruff>=0.8.0,<1.0
```

### Step 5: Create `.env.example`

```bash
# AWS Configuration
AWS_REGION=<your-aws-region>
AWS_ACCESS_KEY_ID=<value-placeholder>
AWS_SECRET_ACCESS_KEY=<value-placeholder>

# S3
S3_BUCKET=<your-bucket-name>

# Secrets Manager
SECRETS_ARN=<value-placeholder>

# Application
APP_ENV=development
APP_PORT=8080
LOG_LEVEL=info
```

No real values. Secrets use `<value-placeholder>`. Copy to `.env` and fill in.

### Step 6: Create `.gitignore`

```
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
*.egg

# Virtual environment
.venv/
venv/

# Testing
.pytest_cache/
coverage/
htmlcov/
.coverage

# Linting / type checking
.mypy_cache/
.ruff_cache/

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

### Step 7: Create `src/data/models.py` with starter Pydantic models

```python
from enum import Enum

from pydantic import BaseModel, Field


class Status(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")


class ErrorResponse(BaseModel):
    detail: str
    status_code: int
```

### Step 8: Create `src/api/app.py` entry point

```python
import os

from dotenv import load_dotenv
from fastapi import FastAPI

from src.data.models import HealthResponse

load_dotenv()

app = FastAPI(
    title=os.getenv("APP_TITLE", "My API"),
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
```

### Step 9: Create `bootstrap.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

MIN_PYTHON="3.12"

echo "=== Checking Python version ==="
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
if [ "$(printf '%s\n' "$MIN_PYTHON" "$PYTHON_VERSION" | sort -V | head -n1)" != "$MIN_PYTHON" ]; then
    echo "ERROR: Python ${MIN_PYTHON}+ required, found ${PYTHON_VERSION}"
    exit 1
fi
echo "Python ${PYTHON_VERSION} OK"

echo "=== Creating virtual environment ==="
python3 -m venv .venv
source .venv/bin/activate

echo "=== Installing dependencies ==="
pip install --upgrade pip
pip install -r requirements-dev.txt

echo "=== Running linter ==="
ruff check src/ tests/

echo "=== Running tests ==="
pytest tests/ -v --tb=short

echo ""
echo "Done. Activate with: source .venv/bin/activate"
```

```bash
chmod +x bootstrap.sh
```

### Step 10: Create `tests/conftest.py`

```python
import os

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def app_client():
    from httpx import ASGITransport, AsyncClient

    from src.api.app import app

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| `src/` for production code, `tests/` for tests — never mixed | Clean separation; `tests/` mirrors `src/` structure for discoverability |
| Every directory needs `__init__.py` | Required for Python package imports to work |
| `requirements.txt` vs `requirements-dev.txt` kept separate | Production image only installs `requirements.txt`; dev deps stay off Fargate |
| `.env.example` shows variable names only, `<value-placeholder>` for secrets | Prevents accidental secret commits; documents expected env vars |
| No hard-coded secrets anywhere | Use `os.environ["KEY"]` for required vars, `os.getenv("KEY", "default")` for optional |
| `os.environ["KEY"]` for required vars | Fails fast at startup if critical config is missing |
| `os.getenv("KEY", "default")` for optional vars | Graceful fallback for non-critical configuration |

---

## Outputs

- Project directory with `src/` and `tests/` package trees
- `requirements.txt` and `requirements-dev.txt` with pinned ranges
- `.env.example` with AWS-specific placeholders
- `.gitignore` covering Python, venv, secrets, IDE files
- `src/data/models.py` with starter enums and Pydantic models
- `src/api/app.py` with FastAPI entry point and health check
- `bootstrap.sh` that validates Python, creates venv, installs deps, lints, and tests
- `tests/conftest.py` with env setup and async test client fixture
