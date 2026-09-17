---
name: backend-python-fastapi
description: >-
  Build or change FastAPI endpoints and their Pydantic/database integrations.
  Use when creating a new FastAPI service, wiring async SQLAlchemy 2.x,
  adding OAuth2/JWT auth, or setting up pytest-asyncio testing. Preserve
  Django and non-FastAPI Python. Schema DDL -> postgres-schema-migrations.
license: Apache-2.0
metadata:
  author: coding-agent
  version: 1.0.12
  category: library-reference
  subcategory: api-reference
  vendor: universal
  lifecycle: active
  coding_agent: true
  tags:
  - library-reference
  - backend
  - python
  - fastapi
  - pydantic
  - sqlalchemy
  - project_level
  audience: developer
  output_format: markdown
  modality: text
---

# Backend Python (FastAPI) -- Production Playbook

For Django services, use `backend-python-django`. For PostgreSQL schema evolution
and migration operations, use `postgres-schema-migrations`; integrate the resulting
database contract with FastAPI dependencies and request handling here.

Build or modernize Python API services with FastAPI, Pydantic v2 and async SQLAlchemy 2.x. Read the target project's interpreter pin, manifest and lockfile before selecting version-specific features. The uv commands below apply to projects managed by uv; preserve another declared manager unless migration is part of the request. Consult the [Python release notes](https://docs.python.org/3/whatsnew/) and [supported-version table](https://devguide.python.org/versions/) when evaluating a runtime upgrade.

**Python web framework landscape** (this skill focuses on FastAPI; consider alternatives if requirements differ):

| Criterion | FastAPI | Django (+ DRF) | Flask | Litestar |
|-----------|---------|----------------|-------|----------|
| **Async native** | Yes | Partial (ASGI in Django 5+) | No (use Quart for async) | Yes |
| **Performance** | High (Starlette/uvicorn) | Moderate | Moderate | High (comparable to FastAPI) |
| **Built-in features** | API-focused (validation, docs) | Full-stack (ORM, admin, auth) | Minimal (micro-framework) | API-focused (DI, validation, docs) |
| **Type safety** | Excellent (Pydantic native) | Growing (type stubs) | Manual | Excellent (native) |
| **Best for** | Modern APIs, microservices | Full-stack web apps, admin-heavy | Simple services, legacy | Modern APIs, DI-heavy architectures |

## Scope
- Creating a new FastAPI service with clean project structure.
- Upgrading a Python backend when a service or dependency requirement justifies the runtime change.
- Implementing async database access with SQLAlchemy 2.0 and Alembic migrations.
- Adding OAuth2/JWT authentication and dependency injection patterns.
- Setting up testing with pytest-asyncio, httpx, and testcontainers.

## Inputs to collect
- Python version: confirm version is pinned (`.python-version`, `pyproject.toml`).
- Package manager: identify the declared manager and lockfile; apply uv commands when `uv.lock` belongs to the project.
- Database: PostgreSQL (default), MySQL, or other.
- Auth requirements: JWT, API key, OAuth2 scopes.
- Deployment target: Docker/Cloud Run/Kubernetes.

## Execution playbook

### Step 1 -- Set up project structure and modern Python features
- Project layout (app factory pattern):
  ```
  src/
    app/
      __init__.py
      main.py              # App factory: create_app()
      config.py            # Pydantic BaseSettings for typed config
      routers/
        __init__.py
        orders.py           # APIRouter for /orders
        health.py           # Health check endpoint
      services/
        order_service.py    # Business logic
      repositories/
        order_repository.py # Data access
      models/
        order.py            # SQLAlchemy models
      schemas/
        order.py            # Pydantic request/response schemas
      middleware/
        auth.py             # Auth middleware
      dependencies/
        db.py               # Database session dependency
        auth.py             # Auth dependency
  migrations/               # Alembic migrations
  tests/
    conftest.py
    test_orders.py
  pyproject.toml
  .python-version           # Pin to project's target version
  ```
- Modern Python features to leverage (verify availability for project version):
  - Improved error messages with fine-grained tracebacks (3.12+).
  - **Free-threaded builds:** Python 3.14 supports this build variant. Select a free-threaded interpreter such as `python3.14t`; `PYTHON_GIL=0` does not convert an ordinary build. Verify native-extension support and application thread safety. See [Python's free-threading guide](https://docs.python.org/3/howto/free-threading-python.html).
  - **Experimental JIT:** on a JIT-capable Python 3.14 build, use `PYTHON_JIT=1` for an explicit experiment and inspect `sys._jit.is_available()` / `is_enabled()`. Free-threaded builds do not support this JIT. Benchmark the actual workload; the [release notes](https://docs.python.org/3.14/whatsnew/3.14.html#binary-releases-for-the-experimental-just-in-time-compiler) do not recommend it for production.
  - **Template strings:** Python 3.14 t-strings produce `Template` objects whose interpolations need a context-specific processor. They do not automatically sanitize SQL, shell or HTML. Retain parameterized queries, argument-array subprocess calls and appropriate HTML escaping. See [PEP 750](https://peps.python.org/pep-0750/).
  - `type` statement for type aliases: `type UserId = int` (3.12+).
  - Improved `typing` module: `TypeVar` defaults (3.13+), `@override` decorator (3.12+), `ReadOnly`/`TypeIs` (3.13+).
  - **FastAPI support:** [FastAPI 0.136.0](https://fastapi.tiangolo.com/release-notes/#01360) added support for Python 3.14t. This does not certify the selected ASGI server, workers, database drivers or native extensions; verify that complete stack before adopting the build.

### Step 2 -- Implement FastAPI with Pydantic v2 and dependency injection
- App factory:
  ```python
  def create_app() -> FastAPI:
      app = FastAPI(title="Order Service", lifespan=lifespan)
      app.include_router(orders_router, prefix="/v1")
      app.include_router(health_router)
      return app
  ```
- Use `lifespan` context manager for startup/shutdown (DB pool, cache connections).
- Pydantic v2 schemas with `model_config`:
  ```python
  class OrderCreate(BaseModel):
      model_config = ConfigDict(strict=True)
      items: list[OrderItemCreate]
      shipping_address_id: UUID

  class OrderResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      id: UUID
      status: OrderStatus
      created_at: datetime
  ```
- Typed settings with `pydantic-settings` and fail-fast validation:
  ```python
  from pydantic import PostgresDsn, SecretStr, field_validator
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
      database_url: PostgresDsn
      jwt_secret: SecretStr
      jwt_algorithm: str = "HS256"
      debug: bool = False
      log_level: str = "INFO"
      cors_origins: list[str] = ["http://localhost:3000"]

      @field_validator("jwt_secret")
      @classmethod
      def secret_min_length(cls, v: SecretStr) -> SecretStr:
          if len(v.get_secret_value()) < 32:
              raise ValueError("jwt_secret must be at least 32 characters")
          return v

  # Fail-fast: validate config at import time, not at first request
  @lru_cache
  def get_settings() -> Settings:
      return Settings()  # raises ValidationError if env is misconfigured
  ```
  Call `get_settings()` inside the `lifespan` or at module level to crash immediately on bad config rather than at first request.
- Dependency injection for services and repos:
  ```python
  async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
      async with request.app.state.session_factory() as session:
          yield session

  async def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
      return OrderService(OrderRepository(db))
  ```

### Step 3 -- Database with SQLAlchemy 2.0 async and Alembic
- SQLAlchemy 2.0 style with `mapped_column`:
  ```python
  class Order(Base):
      __tablename__ = "orders"
      id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
      status: Mapped[OrderStatus] = mapped_column(default=OrderStatus.PENDING)
      created_at: Mapped[datetime] = mapped_column(server_default=func.now())
      items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
  ```
- Async engine and session:
  ```python
  engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20)
  session_factory = async_sessionmaker(engine, expire_on_commit=False)
  ```
- Alembic for migrations: `alembic init -t async migrations`. Configure `env.py` for async. Use `alembic revision --autogenerate -m "add orders table"`. Review autogenerated migrations before applying.
- Repository pattern: keep SQL in repositories, return domain objects to services.

### Step 4 -- Authentication, background tasks, and middleware
- OAuth2 + JWT:
  ```python
  oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")
  async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
      payload = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
      return await user_service.get_by_id(payload["sub"])
  ```
- API key middleware for service-to-service auth.
- Background tasks: use `BackgroundTasks` for lightweight fire-and-forget (email notifications, audit logs). Use Celery or ARQ for reliable, retryable, long-running tasks with a Redis/RabbitMQ broker.
- CORS, rate limiting, and request ID middleware. Add `X-Request-ID` to every response for tracing.
- Error handling hierarchy (RFC 9457 Problem Details):
  ```python
  # Domain exception hierarchy
  class AppError(Exception):
      """Base for all application errors."""
      def __init__(self, code: str, detail: str, status_code: int = 400):
          self.code = code
          self.detail = detail
          self.status_code = status_code

  class NotFoundError(AppError):
      def __init__(self, entity: str, entity_id: str):
          super().__init__("not_found", f"{entity} {entity_id} not found", 404)

  class ConflictError(AppError):
      def __init__(self, detail: str):
          super().__init__("conflict", detail, 409)

  class ForbiddenError(AppError):
      def __init__(self, detail: str = "Forbidden"):
          super().__init__("forbidden", detail, 403)

  # Global exception handler (register in create_app)
  @app.exception_handler(AppError)
  async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
      return JSONResponse(
          status_code=exc.status_code,
          content={
              "type": f"https://api.example.com/errors/{exc.code}",
              "title": exc.code.replace("_", " ").title(),
              "status": exc.status_code,
              "detail": exc.detail,
              "instance": str(request.url),
          },
      )
  ```

### Step 5 -- Health check endpoint
- Implement a health endpoint that verifies downstream dependencies:
  ```python
  # routers/health.py
  from fastapi import APIRouter, Depends, status
  from fastapi.responses import JSONResponse
  from sqlalchemy import text
  from sqlalchemy.ext.asyncio import AsyncSession
  from app.dependencies.db import get_db

  router = APIRouter()

  @router.get("/health", status_code=status.HTTP_200_OK)
  async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
      checks = {}
      try:
          await db.execute(text("SELECT 1"))
          checks["database"] = "ok"
      except Exception:
          checks["database"] = "unhealthy"

      overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
      code = 200 if overall == "ok" else 503
      return JSONResponse(status_code=code, content={"status": overall, "checks": checks})
  ```

### Step 6 -- Testing and profiling
- Testing stack:
  - `pytest` + `pytest-asyncio` (mode=auto) for async tests.
  - `httpx.AsyncClient` with `ASGITransport` for integration tests against the app.
  - `testcontainers` for real PostgreSQL in tests (no SQLite substitution).
  - Fixtures: app factory -> test client -> test database with rollback per test.
- Profiling: use `py-spy` for CPU profiling, `memray` for memory profiling. Benchmark with `locust` or `k6`.

### Step 7 -- Dockerfile and deployment
- Docker multi-stage build with `uv`:
  ```dockerfile
  # -- Build stage -- (match the tag to the version the project declares)
  FROM python:3.13-slim AS builder
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
  WORKDIR /app
  COPY pyproject.toml uv.lock ./
  RUN uv sync --frozen --no-dev --no-install-project
  COPY src/ src/
  RUN uv sync --frozen --no-dev

  # -- Runtime stage --
  FROM python:3.13-slim AS runtime
  ENV PYTHONDONTWRITEBYTECODE=1 \
      PYTHONUNBUFFERED=1
  RUN adduser --disabled-password --no-create-home appuser
  WORKDIR /app
  COPY --from=builder /app/.venv .venv/
  COPY --from=builder /app/src src/
  USER appuser
  EXPOSE 8000
  HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
      CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
  ENTRYPOINT [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
- Production runner: use `uvicorn` with `--workers` flag or behind `gunicorn` for multi-worker production.
- Graceful shutdown: handle SIGTERM, drain connections, complete in-flight requests.
- Set `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1` in container.

## Deliverables / Definition of Done (Acceptance Checklist)
- Project follows the app factory pattern with routers, services, repositories, and schemas.
- Pydantic v2 schemas validate all inputs; typed settings load from environment.
- SQLAlchemy 2.0 async models with Alembic migrations are tested against real PostgreSQL.
- Auth (JWT/API key) is implemented and tested.
- Docker multi-stage build runs with health checks and graceful shutdown.

## Common pitfalls
- Using sync database drivers in async FastAPI (blocks the event loop).
- Sharing SQLAlchemy sessions across requests (use per-request session factory).
- Not running Alembic migrations in CI/CD pipeline.
- Using SQLite in tests instead of real PostgreSQL (misses constraint and type differences).
- Free-threaded mode with thread-unsafe C extensions causing data corruption.

## Example prompts
- "Create a FastAPI order service with async SQLAlchemy, Alembic, and JWT auth."
- "Add testcontainers-based integration tests for our FastAPI endpoints."
- "Refactor our FastAPI app to use the app factory pattern with dependency injection."

## Reference files
Load these from `references/` only when the task needs the deeper detail:
- **[`references/FASTAPI_PROJECT_PATTERNS.md`](references/FASTAPI_PROJECT_PATTERNS.md)** -- read when building the app factory, dependency-injection graph, Pydantic v2 schemas/typed settings, or async/background-task patterns in full.
- **[`references/PYTHON_313_FEATURES.md`](references/PYTHON_313_FEATURES.md)** -- consult before enabling free-threaded (no-GIL) mode, the JIT compiler, or other 3.13+ language features for a specific workload.

## Invocation
- Prefer implicit selection.
- To explicitly request: **Use the `backend-python-fastapi` skill**.

## Official documentation

<!-- FRESHNESS: Always verify against official docs. Links may change. -->

- **FastAPI**: https://fastapi.tiangolo.com/ | release notes: https://fastapi.tiangolo.com/release-notes/
- **Pydantic v2**: https://docs.pydantic.dev/latest/
- **SQLAlchemy 2.x (async)**: https://docs.sqlalchemy.org/en/20/ | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Alembic**: https://alembic.sqlalchemy.org/
- **uvicorn**: https://www.uvicorn.org/ | **granian** (Rust ASGI server): https://github.com/emmett-framework/granian
- **Python status / release schedule**: https://devguide.python.org/versions/ | What's New: https://docs.python.org/3/whatsnew/
- **Alternative frameworks**: Django (https://www.djangoproject.com/), Flask (https://flask.palletsprojects.com/), Litestar (https://litestar.dev/)
- **uv (package manager)**: https://docs.astral.sh/uv/
- **pytest**: https://docs.pytest.org/ | **pytest-asyncio**: https://pytest-asyncio.readthedocs.io/
- **testcontainers-python**: https://testcontainers-python.readthedocs.io/

## Dependency Currency

- **Python 3.14** (GA October 2025; latest 3.14.6 as of 2026-06-10) is the latest stable; supported through October 2030. **Python 3.13** is in full bugfix support until roughly **October 2026** (two years after its 2024-10-07 release), then moves to security-only fixes through its October 2029 EOL (latest patch 3.13.14, also 2026-06-10). **Python 3.15** is in pre-release, planned for October 2026. Python 3.12 has moved to security-only maintenance.
- **FastAPI 0.141.1** is current as of 2026-08-10 (released 2026-07-29; the official release-notes page lists it after 0.141.0). The 0.136.0 release, 2026-04-16, added the free-threaded Python 3.14t support referenced above. FastAPI remains pre-1.0; pin a minor version and audit release notes per upgrade.
- **Pydantic v2** is the current major line (v1 is unsupported, and its `pydantic.v1` compatibility shim is not available at all on Python 3.14+); latest is the 2.13.x line (2.13.4, 2026-05-06). Use `model_config = ConfigDict(...)`, `field_validator`, and `pydantic-settings` for BaseSettings.
- **SQLAlchemy 2.x** is the current major line (latest 2.0.51, 2026-06-15; 2.1 exists only as a beta, not GA); use `AsyncSession`, `mapped_column`, and the 2.0-style `select()` API. Asyncpg is the recommended PostgreSQL driver for async.
- Use **`uv`** (latest 0.11.33) for env/deps (`uv sync`, `uv run`) and lockfile; install into a venv at `.venv/` inside Docker.
- Verify Python version against `.python-version` and `pyproject.toml`.
- Confirm FastAPI, Pydantic, SQLAlchemy, and uvicorn versions against official docs; record pinned versions in `control_docs/SYSTEM_DESIGN.md`.
