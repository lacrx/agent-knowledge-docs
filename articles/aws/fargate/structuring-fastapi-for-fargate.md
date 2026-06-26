---
title: Structuring FastAPI for Fargate
topics:
  - fastapi
  - aws
  - fargate
  - python
  - web-applications
skills:
  - scaffold-fastapi
  - create-python-dockerfile
  - provision-fargate-task
summary: >
  Architecture patterns for structuring FastAPI applications to run reliably on AWS Fargate, covering project layout, container concerns, and AWS integration points.
aliases:
  - fastapi fargate structure
  - fastapi project layout fargate
  - fastapi ecs architecture
related:
  - deploying-python-web-apps-to-fargate
  - structuring-nextjs-server-for-fargate
last-updated: 2026-06-25
---

# Structuring FastAPI for Fargate

## Overview

Running FastAPI on Fargate is straightforward at the container level — uvicorn serves requests, Fargate keeps the container alive — but the internal structure of the application determines how maintainable, testable, and operationally sound the deployment is. Decisions about where to put business logic, how to handle startup work, how to expose health information, and how to manage configuration all have downstream effects on deployment reliability and debugging speed.

This article covers architecture patterns for FastAPI projects targeting Fargate. It is advisory, not procedural: the focus is on why certain structures work better than others in a Fargate environment and what trade-offs each choice carries. The companion skills cover the executable steps.

> **Skill:** For step-by-step scaffolding, use the `scaffold-fastapi` skill. For containerization, use the `create-python-dockerfile` skill. For Fargate task provisioning, use the `provision-fargate-task` skill.

---

## Project Layout

A FastAPI project bound for Fargate should separate concerns clearly enough that each layer can be tested, replaced, or scaled independently. A layout that works well:

```
project/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app instance, middleware, lifecycle hooks
│   ├── config.py           # Settings loaded from environment
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py       # Health and readiness endpoints
│   │   ├── api_v1.py       # Versioned API routes
│   │   └── webhooks.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── orders.py       # Business logic, no HTTP awareness
│   ├── models/
│   │   ├── __init__.py
│   │   └── domain.py       # Pydantic models, DB models
│   └── dependencies.py     # FastAPI Depends callables
├── tests/
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

### Key Boundaries

**`main.py` is the composition root, not the business logic.** It creates the `FastAPI()` instance, registers routers, attaches middleware, and defines lifecycle hooks. It should not contain route handlers, database queries, or transformation logic. When `main.py` grows past 100 lines, it usually means responsibilities are leaking in.

**Routes are thin.** Route handlers validate input (via Pydantic), call a service function, and return the result. They should not contain branching business logic, direct database calls, or SDK interactions. This makes routes testable with simple dependency overrides.

**Services are HTTP-unaware.** A service function receives typed arguments and returns typed results. It does not know about `Request`, `Response`, or `HTTPException`. This lets you reuse service logic in background tasks, CLI tools, or other entry points without importing FastAPI.

**Dependencies manage lifecycle.** Database sessions, HTTP clients, and SDK clients are created as FastAPI dependencies. This gives you automatic cleanup, request-scoped isolation, and easy test overrides.

---

## App Entry Point and Process Model

### The `app` Object

Fargate's task definition points uvicorn at the app object. The import path matters:

```dockerfile
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Define `app` at module level in `main.py`. Do not create it inside a function or behind a conditional — uvicorn imports it directly, and lazy creation causes confusing startup failures in containers.

### Workers and Concurrency

Uvicorn can run with multiple worker processes via `--workers`. On Fargate, size the worker count to the allocated CPU:

| Fargate CPU | Recommended Workers | Rationale |
|---|---|---|
| 256 (0.25 vCPU) | 1 | Single core, multiple workers waste memory |
| 512 (0.5 vCPU) | 2 | Modest concurrency gain |
| 1024 (1 vCPU) | 2-3 | Diminishing returns past 3 due to GIL |
| 2048 (2 vCPU) | 3-4 | Balance throughput and memory |

Each uvicorn worker duplicates the full application in memory. Overprovisioning workers relative to available memory triggers OOM kills, which Fargate reports only as a task stopping with exit code 137 and no application-level error.

For async-heavy workloads (many I/O-bound requests, few CPU-bound operations), a single worker with uvicorn's default async event loop often outperforms multiple workers because async coroutines multiplex within the event loop without duplicating memory.

### Port Binding

Always bind to `0.0.0.0`. Fargate uses `awsvpc` networking — each task gets its own ENI. Binding to `127.0.0.1` makes the application unreachable from the ALB health checker and all external traffic.

---

## Startup and Shutdown Lifecycle

FastAPI's lifespan context manager is the correct place for container-lifecycle work:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize pools, warm caches, verify connectivity
    db_pool = await create_pool(settings.DATABASE_URL)
    app.state.db_pool = db_pool
    yield
    # Shutdown: drain connections, flush buffers
    await db_pool.close()
```

```python
app = FastAPI(lifespan=lifespan)
```

### What Belongs in Startup

- Database connection pool creation
- HTTP client session initialization (e.g., `httpx.AsyncClient`)
- Cache warming if the app is unusable without it
- Verification that required secrets are present (fail fast with a clear error)

### What Does Not Belong in Startup

- Heavy data loads that take minutes — these cause the ALB health check to time out, marking the task unhealthy before it finishes starting
- Import-time side effects like database connections at module level — these run during `import`, before the lifespan hook, and before environment variables from Secrets Manager are injected
- Blocking synchronous calls — these block the event loop and delay startup of all workers

### Shutdown Behavior

Fargate sends SIGTERM when stopping a task, then waits for `stopTimeout` seconds (default 30) before sending SIGKILL. Uvicorn catches SIGTERM and initiates graceful shutdown. Your lifespan's cleanup code (after `yield`) runs during this window. Keep cleanup fast — if it takes longer than the stop timeout, the process is killed mid-cleanup, leaving connections in a broken state.

---

## Health Endpoints

Fargate deployments depend on ALB health checks to determine task health. A minimal health endpoint that just returns 200 tells the ALB nothing useful. A good health endpoint checks that the application can actually serve requests:

```python
@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception:
        raise HTTPException(status_code=503, detail="database unreachable")
```

### Liveness vs. Readiness

Consider exposing two health endpoints:

| Endpoint | Purpose | What It Checks |
|---|---|---|
| `/health/live` | Is the process running? | Returns 200 if the app can respond at all |
| `/health/ready` | Can the process serve traffic? | Checks DB, cache, and external service connectivity |

Point the ALB health check at `/health/ready`. Use `/health/live` for container-level health checks in the Dockerfile (`HEALTHCHECK`) or for monitoring systems.

### Avoiding Health Check Storms

If your readiness check queries a database, and you have 10 tasks with 30-second health check intervals, that is 20 extra queries per minute. For most databases this is negligible, but if your health check does something expensive (running a complex query, calling an external API), the overhead scales linearly with task count. Keep health checks fast and cheap.

---

## Configuration and Secrets

### Environment-Based Configuration

Use Pydantic's `BaseSettings` to load configuration from environment variables. This gives you type validation, default values, and a single source of truth:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    log_level: str = "INFO"
    allowed_origins: list[str] = ["*"]

    model_config = {"env_prefix": ""}
```

Instantiate `Settings` once in `config.py` and import it. Do not call `Settings()` in multiple places — each call re-reads the environment, and inconsistencies are hard to debug.

### Secrets Injection

ECS injects secrets from AWS Secrets Manager or SSM Parameter Store as environment variables at task startup. From the application's perspective, they are indistinguishable from regular environment variables. The critical rule: never bake secrets into the Docker image. Even values in `.env` files that get copied into the image are visible in the image layers.

Keep the `config.py` module simple — it should read from the environment, not from files or secret managers directly. Let ECS handle the injection.

> **Skill:** For setting up secrets in AWS, use the `provision-secrets-manager` skill.

---

## Route Organization

### Router-Based Composition

Use `APIRouter` instances to group related routes, then include them in the main app:

```python
# routes/api_v1.py
router = APIRouter(prefix="/api/v1", tags=["v1"])

@router.get("/orders")
async def list_orders(service: OrderService = Depends(get_order_service)):
    return await service.list_orders()
```

```python
# main.py
from app.routes import health, api_v1
app.include_router(health.router)
app.include_router(api_v1.router)
```

This keeps `main.py` declarative and makes it obvious which URL paths exist by looking at the router registrations.

### Versioning

Prefix routers with `/api/v1`, `/api/v2`, etc. On Fargate, you cannot do path-based routing at the ALB level without additional listener rules. Keeping versions inside the application is simpler and avoids ALB configuration churn when you add new API versions.

---

## Service Layer Separation

The service layer is where business logic lives. Separating it from routes has concrete benefits in a Fargate context:

**Testability.** Service functions take typed inputs and return typed outputs. You can test them without spinning up a FastAPI test client or mocking HTTP internals.

**Reusability across entry points.** A Fargate deployment might run both an API service and a background worker. If business logic is in route handlers, the worker cannot use it without importing the entire web framework. If it is in service functions, both entry points can share the same logic.

**Clearer error boundaries.** Service functions raise domain exceptions (e.g., `OrderNotFoundError`). Route handlers catch these and translate them to HTTP responses. This prevents leaking HTTP semantics into business logic and makes error handling consistent across multiple routes that call the same service.

```python
# services/orders.py
class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_order(self, order_id: str) -> Order:
        order = await self.db.get(Order, order_id)
        if not order:
            raise OrderNotFoundError(order_id)
        return order
```

```python
# routes/api_v1.py
@router.get("/orders/{order_id}")
async def get_order(order_id: str, service: OrderService = Depends(get_order_service)):
    try:
        return await service.get_order(order_id)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
```

---

## Templates and Static Assets

If your FastAPI app serves HTML templates (Jinja2) or static files, container deployment adds constraints:

**Static files should be served by the ALB or a CDN, not by FastAPI.** FastAPI's `StaticFiles` mount works but consumes application CPU and memory for byte-serving. In a Fargate setup, upload static assets to S3 and serve them through CloudFront. Reserve FastAPI for dynamic content.

**If you must serve static files from the container** (internal tools, admin interfaces), mount them with a cache-control header so the ALB and browsers cache aggressively:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
```

**Templates are fine to bundle in the image.** Jinja2 templates are small text files that load quickly. Include them in the Docker build context and reference them with a relative path from the working directory.

---

## Logging for CloudWatch

Fargate captures stdout/stderr and forwards it to CloudWatch Logs via the `awslogs` driver. Structure your logging to make CloudWatch Insights queries possible:

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record),
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.root.addHandler(handler)
logging.root.setLevel(logging.INFO)
```

Avoid `print()` statements — they bypass the logging framework and produce unstructured output that is difficult to filter. Avoid logging to files inside the container — those files disappear when the task stops, and they consume the task's ephemeral storage allocation.

> **Skill:** For querying CloudWatch logs, use the `query-aws-logs` skill.

---

## Single Service vs. Split Responsibilities

A common Fargate architecture question: should a FastAPI app handle both API requests and background tasks (via `asyncio.create_task` or in-process queues), or should these be separate services?

### Single Service

- Simpler deployment: one image, one task definition
- Lower cost at small scale: no idle background worker
- Risk: a slow background task can starve the event loop, increasing API latency
- Risk: scaling the API also scales background processing, which may not be desirable

### Split Services

- API service and worker service share the same codebase but run different entry points
- API scales independently based on request load; worker scales based on queue depth
- Requires a queue (SQS) or event bus (EventBridge) between them
- More infrastructure to manage, but each service has clear resource boundaries

**Recommendation:** Start with a single service if background work is lightweight and infrequent (sending emails, writing audit logs). Split when background work is CPU-intensive, long-running, or needs independent scaling. The service-layer separation described above makes the split straightforward when the time comes — you move the worker entry point to a separate module that imports the same service functions.

---

## Common Mistakes

| Mistake | Impact | Fix |
|---|---|---|
| Business logic in `main.py` | Untestable, unshareable across entry points | Move to `services/` layer with typed inputs/outputs |
| Expensive work at import time | Crashes before env vars are injected; slows cold start | Move to lifespan startup hook |
| Health check returns 200 unconditionally | ALB routes traffic to broken instances | Check actual dependencies (DB, cache) in health endpoint |
| Secrets in `.env` file copied into image | Credentials visible in image layers | Use ECS secrets block with Secrets Manager |
| Calling `Settings()` in multiple modules | Inconsistent config, repeated env reads | Instantiate once in `config.py`, import the instance |
| Synchronous blocking calls in async routes | Event loop blocked, all requests stall | Use `run_in_executor` or async-native libraries |
| Logging to files instead of stdout | Logs lost when task stops | Log to stdout with JSON formatter |
| No graceful shutdown handler | Connections dropped, data lost | Use lifespan context manager for cleanup |
| Serving large static assets from FastAPI | Wastes CPU, slow delivery | Serve from S3 + CloudFront, or ALB redirect |
| Over-provisioning uvicorn workers | OOM kills with exit code 137 | Match worker count to Fargate CPU/memory allocation |

---

## References

- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [AWS Fargate Task Definition Parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Pydantic Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic-settings/)
