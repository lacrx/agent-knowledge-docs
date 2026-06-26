---
name: scaffold-fastapi
title: Scaffold FastAPI
type: skill
topics:
  - python
  - fastapi
  - scaffolding
  - aws
  - fargate
summary: >
  Scaffold the FastAPI application layer on top of an already-scaffolded Python project.
  Covers JSON API routes, Jinja2 HTML templates, static files, health check, and lifespan.
references:
  - articles/agent-workflow/anthropic-sdk-fastapi-tools.md
  - skills/scaffold-python-project.md
  - skills/create-python-dockerfile.md
  - articles/aws/fargate/structuring-fastapi-for-fargate.md
  - articles/aws/python-project-scaffolding-aws.md
last-updated: 2026-06-13
---

# Scaffold FastAPI

Build the FastAPI application layer on an existing Python project (from scaffold-python-project).
Follow steps in order.

---

## Prerequisites

- Python project already scaffolded via `scaffold-python-project` (`src/`, `tests/`, `.venv/` exist)
- `requirements.txt` includes: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`
- Virtual environment activated

Add Jinja2 if not already present:

```bash
echo "jinja2>=3.1.0,<4.0" >> requirements.txt
echo "python-multipart>=0.0.12,<1.0" >> requirements.txt
pip install -r requirements.txt
```

---

## Steps

### Step 1: Create route directory

```bash
mkdir -p src/api/routes
touch src/api/routes/__init__.py
```

### Step 2: Create health check route — `src/api/routes/health.py`

```python
from fastapi import APIRouter

from src.data.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
```

Returns 200 immediately. No database or external dependency checks — this
endpoint must never fail due to a downstream service.

### Step 3: Create web route with Jinja2 templates — `src/api/routes/web.py`

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="src/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "title": "Dashboard"},
    )
```

`request` must always be passed in the template context — Jinja2Templates
requires it for URL generation and CSRF.

### Step 4: Create app entry point — `src/api/app.py`

```python
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes.health import router as health_router
from src.api.routes.web import router as web_router

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: initialize shared resources here
    yield
    # Shutdown: clean up resources here


app = FastAPI(
    title=os.getenv("APP_TITLE", "My App"),
    description="FastAPI application",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Health check first — always reachable
app.include_router(health_router)

# Web routes last — catch-all / route must not shadow API routes
app.include_router(web_router)
```

Key rules:
- `app.py` contains only wiring — no business logic
- Lifespan context manager, not deprecated `on_startup`/`on_shutdown`
- Health router first, web router last (catch-all `/` route)
- Static files mounted at `/static`

### Step 5: Add feature route pattern

When adding a new feature, create a router file and wire it into `app.py`
with a versioned prefix:

```python
# src/api/routes/items.py
from fastapi import APIRouter

router = APIRouter(tags=["items"])


@router.get("/")
async def list_items():
    return {"items": []}


@router.post("/")
async def create_item():
    return {"id": "new"}
```

Wire into `app.py` between health and web routers:

```python
from src.api.routes.items import router as items_router

# API routes with versioned prefix
app.include_router(items_router, prefix="/api/v1/items")
```

Router registration order in `app.py`:
1. `health_router` — no prefix
2. Feature routers — `/api/v1/{resource}` prefix
3. `web_router` — no prefix (catch-all `/` last)

### Step 6: Create templates directory and base template

```bash
mkdir -p src/templates
```

`src/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}My App{% endblock %}</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <nav>
        <a href="/">Home</a>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
    <script src="/static/js/app.js"></script>
</body>
</html>
```

### Step 7: Create dashboard template — `src/templates/dashboard.html`

```html
{% extends "base.html" %}

{% block title %}{{ title }} — My App{% endblock %}

{% block content %}
<h1>{{ title }}</h1>
<p>Application is running.</p>
{% endblock %}
```

### Step 8: Create static file placeholders

```bash
mkdir -p src/static/css
mkdir -p src/static/js
```

`src/static/css/style.css`:

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: system-ui, -apple-system, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem;
}

nav {
    padding: 1rem 0;
    border-bottom: 1px solid #eee;
    margin-bottom: 2rem;
}

nav a {
    color: #0066cc;
    text-decoration: none;
}
```

`src/static/js/app.js`:

```javascript
// Application JavaScript
```

### Step 9: Create lazy AWS client pattern — `src/api/clients.py`

```python
import os

import boto3


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

AWS/boto3 clients use lazy initialization — never at module import time.
This avoids credential errors during testing and import-time side effects.

### Step 10: Verify

```bash
# Run the app
uvicorn src.api.app:app --host 0.0.0.0 --port 8080 --workers 1

# In another terminal:
curl -f http://localhost:8080/health
curl -f http://localhost:8080/
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| `app.py` contains only wiring | No business logic — keeps the entry point readable and testable |
| Health endpoint returns 200 immediately | No external dependencies — ALB health checks must not fail due to downstream services |
| API routes use `/api/v1/` prefix | Versioned prefix allows breaking changes in `/api/v2/` without affecting existing clients |
| Web router registered last | Catch-all `/` route must not shadow API routes |
| Lifespan context manager | `on_startup`/`on_shutdown` are deprecated in FastAPI |
| `request` always in Jinja2 context | Jinja2Templates requires it for URL generation |
| Port 8080 for Fargate | Must match ECS task definition `containerPort` |
| Single uvicorn worker | Required if any in-memory state; Fargate scales via task count |
| AWS clients use lazy init | Never at module import time — prevents credential errors in tests |

---

## Outputs

- `src/api/app.py` — FastAPI entry point with lifespan, static files, router wiring
- `src/api/routes/health.py` — health check returning 200
- `src/api/routes/web.py` — Jinja2-rendered HTML pages
- `src/api/clients.py` — lazy-initialized AWS client pattern
- `src/templates/base.html` — base HTML template with blocks
- `src/templates/dashboard.html` — dashboard page extending base
- `src/static/css/style.css` — starter stylesheet
- `src/static/js/app.js` — placeholder JavaScript
- `/health` returns 200 OK
- `/` renders dashboard HTML
