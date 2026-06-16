# AMCE — Phase 1: Control Plane Core & Registry Persistence

**Days 13–24 | FastAPI Backend, PostgreSQL 16 Migrations, Contract CRUD, RBAC, GIN Indexing**

---

## Phase Overview

Phase 1 builds the server-side half of AMCE: the authenticated REST API that stores contracts,
manages versions, enforces RBAC, and serves the active schema bundle to SDK clients. It runs
as a FastAPI application (`apps/telemetry-plane`) backed by PostgreSQL 16 with full Row-Level
Security and GIN-indexed JSONB columns.

**Key deliverables:**

- FastAPI application with structured logging, lifespan, CORS, and Alembic migrations
- Multi-tenant schema: `organizations`, `projects`, `users`, `roles`, `contracts`, `contract_versions`, `telemetry_logs`
- GIN indexes on `schema_definition` and `validation_rules` JSONB columns
- Contract CRUD REST API with cursor-based pagination
- Semantic version enforcement and breaking-change detection
- `GET /api/v1/contracts/active` bundle with ETag caching and 60s app-level cache
- API Key authentication with bcrypt + timing-attack jitter
- RBAC (flat permissions, no inheritance) wired to all endpoints
- Token bucket rate limiting (in-process; Redis upgrade in Phase 3)
- Telemetry ingest endpoint (202 Accepted, BackgroundTasks, Kafka stub)
- 60 integration tests, p99 < 100ms under 100 concurrent users

---

## Architecture Position

```
SDK Client (Phase 0)
   │ GET /api/v1/contracts/active  (bootstrap + TTL refresh)
   │ POST /api/v1/telemetry/batch  (fire-and-forget)
   ▼
┌──────────────────────────────────────────────────────────────┐
│                  apps/telemetry-plane  (this phase)           │
│                                                              │
│  ── Middleware Stack (ordered) ──────────────────────────    │
│  1. RequestID       → inject X-Request-ID into context       │
│  2. StructLog       → bind request_id, tenant_id per req     │
│  3. CORS            → configurable origins                   │
│  4. RateLimit       → TokenBucket per API key (in-process)   │
│                                                              │
│  ── Routers ────────────────────────────────────────────     │
│  /api/v1/contracts  → ContractRouter                        │
│  /api/v1/telemetry  → TelemetryRouter  (202 only)           │
│  /health            → HealthRouter                          │
│                                                              │
│  ── Services ───────────────────────────────────────────     │
│  ContractRepository   (asyncpg + SQLAlchemy 2.0)            │
│  VersioningService    (breaking change detection)           │
│  BundleCache          (asyncio.Lock thundering-herd guard)  │
│  AuditLogger          (BackgroundTask, never blocks)        │
│  RBAC                 (flat permissions, DB lookup)         │
│                                                              │
│  ── Auth Layer ─────────────────────────────────────────     │
│  ApiKeyGuard          (prefix lookup + bcrypt.checkpw)      │
│  SessionMiddleware    → SET LOCAL app.current_org_id        │
└────────────────────────────┬─────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  PostgreSQL 16   │
                    │  + RLS policies  │
                    │  + GIN indexes   │
                    └─────────────────┘
```

---

## Source Tree

### MVP Layout — Monorepo + Monolith

> Phase 1 lives entirely inside `apps/telemetry-plane`. The name reflects its future purpose
> (the telemetry plane grows in Phase 2); in Phase 1 it is the control plane monolith.

```
amce-monorepo/
└── apps/
    └── telemetry-plane/
        ├── project.json                   ← Nx: serve, migrate, docker-build targets
        ├── pyproject.toml                 ← hatchling, uv workspace member
        ├── Dockerfile                     ← multi-stage, non-root, health check
        │
        ├── alembic.ini                    ← async DSN from DATABASE_URL env var
        ├── alembic/
        │   ├── env.py                     ← async engine + RLS session setup
        │   └── versions/
        │       ├── 001_initial_schema.py  ← Day 14: orgs, projects, users, roles, RLS
        │       ├── 002_contracts.py       ← Day 15: contracts, contract_versions, GIN
        │       ├── 003_telemetry_rbac.py  ← Day 16: telemetry_logs, api_keys, audit_logs
        │       ├── 004_telemetry_dlq.py   ← Day 23: telemetry_dlq table
        │       └── ...                    ← Phase 2/3 migrations added here
        │
        └── src/
            └── amce_telemetry/
                ├── __init__.py
                ├── main.py                ← FastAPI app, lifespan, middleware stack
                │
                │   ── Configuration ──
                ├── settings.py            ← pydantic-settings: DATABASE_URL,
                │                             KAFKA_*, CLICKHOUSE_*, REDIS_URL,
                │                             AMCE_CORS_ORIGINS, AMCE_ENV
                │
                │   ── Database Layer ──
                ├── database.py            ← asyncpg engine, session factory,
                │                             SET LOCAL app.current_org_id helper,
                │                             connection pool lifecycle
                │
                │   ── Auth Layer ──
                ├── auth/
                │   ├── __init__.py
                │   ├── api_key_guard.py   ← FastAPI Depends: prefix split,
                │   │                         bcrypt.checkpw, 1–5ms jitter on fail,
                │   │                         audit log on AUTH_FAILED
                │   ├── rbac.py            ← permission_required(perm) dependency factory
                │   │                         flat permissions JSONB array lookup
                │   │                         permission set aggregated at auth time
                │   └── permissions.py     ← string constants: CONTRACT_READ,
                │                             CONTRACT_WRITE, CONTRACT_PUBLISH,
                │                             TELEMETRY_READ, ADMIN_ALL
                │
                │   ── Middleware ──
                ├── middleware/
                │   ├── __init__.py
                │   ├── request_id.py      ← inject X-Request-ID (UUID4)
                │   ├── structlog_ctx.py   ← bind request_id + tenant_id to log context
                │   └── rate_limit.py      ← TokenBucket per API key
                │                             asyncio.Lock per key (no race)
                │                             X-RateLimit-* response headers
                │                             LRU evict bucket dict at 10K keys
                │
                │   ── Schemas (Pydantic request/response) ──
                ├── schemas/
                │   ├── __init__.py
                │   ├── contracts.py       ← CreateContractRequest, ContractResponse,
                │   │                         ContractDetailResponse, UpdateContractRequest,
                │   │                         PaginatedContractsResponse, CursorPage
                │   ├── versions.py        ← PublishVersionRequest, VersionResponse,
                │   │                         BreakingChangeReport
                │   └── telemetry.py       ← TelemetryEventRequest, TelemetryBatchRequest
                │
                │   ── Routers ──
                ├── routers/
                │   ├── __init__.py
                │   ├── health.py          ← GET /health (liveness)
                │   │                         GET /health/deep (readiness: DB + Kafka ping)
                │   ├── contracts.py       ← POST   /api/v1/contracts
                │   │                         GET    /api/v1/contracts (paginated, cursor)
                │   │                         GET    /api/v1/contracts/{id}
                │   │                         PUT    /api/v1/contracts/{id}
                │   │                         PATCH  /api/v1/contracts/{id}/status
                │   │                         POST   /api/v1/contracts/{id}/versions
                │   │                         POST   /api/v1/contracts/{id}/versions/{v}/activate
                │   │                         GET    /api/v1/contracts/active
                │   └── telemetry.py       ← POST /api/v1/telemetry (202 Accepted)
                │
                │   ── Services ──
                └── services/
                    ├── __init__.py
                    ├── contract_repository.py  ← AsyncSession CRUD:
                    │                              create(), get_by_id(), list_by_project()
                    │                              get_active_version(), publish_version()
                    │                              optimistic locking on PUT (updated_at)
                    │                              SELECT FOR UPDATE on version activate
                    ├── versioning.py            ← VersionCompatibilityChecker:
                    │                              is_breaking_change() → BreakingChangeReport
                    │                              8 breaking change categories
                    │                              MAJOR/MINOR/PATCH bump enforcement
                    ├── bundle_cache.py          ← 60s app-level cache (asyncio.Lock)
                    │                              ETag: SHA-256 of serialised bundle
                    │                              Cache-Control: max-age=60, must-revalidate
                    │                              thundering-herd guard (1 DB fetch for N waiters)
                    │                              invalidate() on version activation
                    └── audit_logger.py          ← AuditLogger.log() → BackgroundTask INSERT
                                                   actions: CONTRACT_CREATED, VERSION_PUBLISHED,
                                                   ROLE_ASSIGNED, RATE_LIMIT_BREACH, AUTH_FAILED

        └── tests/
            ├── conftest.py                ← per-test transaction rollback fixture,
            │                                mock Kafka producer, async test client
            ├── unit/
            │   ├── test_auth.py           ← Day 16: API key guard, bcrypt timing
            │   ├── test_middleware.py     ← Day 21: rate limit, X-RateLimit headers, CORS order
            │   └── test_rbac.py           ← Day 22: permission enforcement per endpoint
            ├── api/
            │   ├── test_contracts.py      ← Day 17: CRUD, pagination, schema injection guard
            │   ├── test_versioning.py     ← Day 18: breaking change detection, semver enforcement
            │   └── test_telemetry.py      ← Day 23: 202 response time, DLQ fallback, dedup
            ├── db/
            │   ├── test_migration_001.py  ← verify all tables + RLS after each migration
            │   ├── test_migration_002.py
            │   ├── test_contract_repository.py ← CRUD + concurrent publish
            │   └── test_query_plans.py    ← EXPLAIN ANALYZE: zero Seq Scans
            └── integration/
                └── phase1_suite.py        ← Day 24: 60-test sign-off suite
```

### Future Microservice Extraction Path

> Phase 1's monolith maps cleanly onto two future microservices. The extraction boundary
> is the `routers/` split — each router becomes its own service with its own DB connection pool.

```
[MVP]  apps/telemetry-plane (monolith)
         ├── routers/contracts.py    ┐
         ├── services/contract_*     ├─→ [MSvc] svc-contract-registry
         ├── alembic/versions/001-002┘     own DB pool, own migrations
         │
         ├── routers/telemetry.py    ┐
         └── services/audit_logger   └─→ [MSvc] svc-telemetry-ingestion
                                          (grows significantly in Phase 2)

# Auth layer (api_key_guard, rbac) extracts to:
#   [MSvc] svc-auth-gateway   OR   shared middleware lib in libs/
#
# Migration strategy:
#   1. Add X-Service-Token internal header to svc-contract-registry
#   2. svc-validation-gateway calls svc-contract-registry for schema fetches
#   3. Deploy as separate Kubernetes Deployments with shared PostgreSQL RDS
#   4. Migrate alembic to per-service migration namespaces
```

---

## Database Schema

### Migration 001 — Core Identity (Day 14)

```sql
-- organizations: one row per tenant
CREATE TABLE organizations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    slug          VARCHAR(100) NOT NULL UNIQUE,
    api_key_hash  VARCHAR(255) NOT NULL CHECK(LENGTH(api_key_hash) >= 60),
    plan          VARCHAR(50)  NOT NULL DEFAULT 'free'
                  CHECK(plan IN ('free','pro','enterprise')),
    region        VARCHAR(10)  NOT NULL DEFAULT 'US'
                  CHECK(region IN ('US','EU','APAC')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON organizations
    USING (id = current_setting('app.current_org_id')::uuid);

-- projects: namespace within an org
CREATE TABLE projects (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name       VARCHAR(255) NOT NULL,
    slug       VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, slug)
);
CREATE INDEX idx_projects_org ON projects(org_id);
-- (users, roles, user_roles follow same RLS pattern)
```

### Migration 002 — Contract Registry (Day 15)

```sql
CREATE TABLE contracts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES organizations(id),
    project_id  UUID NOT NULL REFERENCES projects(id),
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    status      VARCHAR(50) NOT NULL DEFAULT 'draft'
                CHECK(status IN ('active','deprecated','draft')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_contracts_tenant  ON contracts(tenant_id);
CREATE INDEX idx_contracts_project ON contracts(project_id);

CREATE TABLE contract_versions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id       UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    version           VARCHAR(50) NOT NULL,
    schema_definition JSONB NOT NULL CHECK(jsonb_typeof(schema_definition) = 'object'),
    validation_rules  JSONB,
    is_active         BOOLEAN NOT NULL DEFAULT FALSE,
    published_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(contract_id, version)
);

-- GIN indexes — the hot query path
CREATE INDEX idx_cv_schema_gin ON contract_versions
    USING GIN (schema_definition jsonb_path_ops);
CREATE INDEX idx_cv_rules_gin  ON contract_versions
    USING GIN (validation_rules  jsonb_path_ops);

-- Partial index: active versions only (high selectivity)
CREATE INDEX idx_cv_active ON contract_versions(contract_id, id)
    WHERE is_active = TRUE;
```

---

## Day-by-Day Implementation Plan

### Day 13 — FastAPI Scaffold, Lifespan, structlog, CORS, Health Endpoint, Alembic Init

**Core objective:** Stand up a production-grade FastAPI skeleton with JSON structured logging,
health probes ready for Kubernetes, and the Alembic migration infrastructure.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/main.py`
- `apps/telemetry-plane/src/amce_telemetry/settings.py`
- `apps/telemetry-plane/src/amce_telemetry/database.py`
- `apps/telemetry-plane/src/amce_telemetry/routers/health.py`
- `apps/telemetry-plane/alembic.ini` + `alembic/env.py`

**structlog configuration (idempotent, guarded by `_configured` flag):**

```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),   # production
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
```

**Middleware stack order (critical — see Day 21 for rationale):**

```
1. RequestID      (must be first — sets X-Request-ID for all downstream)
2. StructLog ctx  (binds request_id from step 1)
3. CORS           (must be before rate limit — OPTIONS must always get CORS headers)
4. Rate Limit     (keyed by API key extracted later)
```

**Critical edge cases:**

- Lifespan DB failure: re-raise to prevent FastAPI from starting on broken instance
- `AMCE_CORS_ORIGINS='*'` in production: log CRITICAL warning — wildcard prohibited
- Health endpoint: wrap all dependency checks in try/except — never raise 500 from `/health`
- structlog `configure()` called twice: `_configured` guard prevents processor duplication

**Verification:**

```bash
nx serve telemetry-plane
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0","db_connected":true,"timestamp":"..."}

pytest tests/unit/test_main.py::test_health -v
```

---

### Day 14 — Migration 001: Organizations, Projects, Users, Roles, RLS Policies

**Core objective:** Lay the complete multi-tenant identity schema. RLS is mandated from the
first migration — there is no "we'll add RLS later" in AMCE.

**Session variable pattern (set on every authenticated request):**

```python
await session.execute(
    text("SET LOCAL app.current_org_id = :tid"),
    {"tid": str(org_id)}
)
# SET LOCAL is transaction-scoped — automatically cleared on commit/rollback
```

**Critical edge cases:**

- `FORCE ROW LEVEL SECURITY`: prevents superuser bypass — mandatory on all tables
- `api_key_hash` CHECK: `LENGTH(api_key_hash) >= 60` — raw keys never stored
- Cascade deletes: `org DELETE → projects DELETE → contracts DELETE` — test explicitly
- `plan` as CHECK constraint not ENUM type: avoids migration complexity on new tiers

**Verification:**

```bash
make migrate  # alembic upgrade head
make psql
# \d organizations  → verify all columns + constraints

# RLS isolation test
SET app.current_org_id = '<org-a-uuid>';
-- INSERT a row for org-b, then SELECT * → returns 0 rows
```

---

### Day 15 — Migration 002: contracts + contract_versions, JSONB + GIN Indexes

**Core objective:** The contract registry schema is the central data store for the entire system.
GIN indexes must be verified with EXPLAIN ANALYZE before this day is signed off.

**Query that must use GIN (verify with EXPLAIN):**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, schema_definition
FROM contract_versions
WHERE schema_definition @> '{"type": "object"}'::jsonb
  AND is_active = TRUE;
-- Expected: Bitmap Heap Scan via idx_cv_schema_gin — NEVER Seq Scan
```

**Critical edge cases:**

- JSONB `null` vs SQL NULL: `CHECK(jsonb_typeof(schema_definition) = 'object')` prevents JSON `null`
- Concurrent version publishing: `SELECT FOR UPDATE` on contract row serialises the transaction
- `schema_definition` max size: enforce 100KB application-level limit in `CreateContractRequest`
- Partial index `idx_cv_active`: only indexes `is_active=TRUE` rows — document in code comments

**Repository methods:**

```python
# All methods require tenant session variable to be set before call
async def get_active_version(self, contract_id: UUID) -> ContractVersion | None
async def publish_version(self, contract_id: UUID, version: str,
                           schema_def: dict) -> ContractVersion
async def activate_version(self, contract_id: UUID, version_id: UUID) -> None
    # Uses SELECT FOR UPDATE — serialises concurrent activations
```

---

### Day 16 — Migration 003: telemetry_logs, RBAC Schema, ApiKeyGuard with bcrypt

**Core objective:** Build the authentication and authorization backbone. Every subsequent endpoint
depends on `ApiKeyGuard` and `permission_required`.

**API key structure:** `{prefix_8_chars}.{secret_32_chars}`

- `prefix` stored in plaintext for fast lookup
- `secret` bcrypt-hashed at creation time
- Lookup: `WHERE key_prefix = :prefix AND is_active = TRUE AND (expires_at IS NULL OR expires_at > NOW())`

**Timing attack prevention:**

```python
# 1-5ms random jitter on failed lookups — prevents prefix enumeration
if not bcrypt.checkpw(secret.encode(), row.key_hash.encode()):
    await asyncio.sleep(random.uniform(0.001, 0.005))
    raise HTTPException(status_code=403, detail="Invalid API key")
```

**RBAC permission check flow:**

```
Request arrives →
  ApiKeyGuard extracts org_id from api_keys table →
  SET LOCAL app.current_org_id = org_id →
  permission_required("CONTRACT_WRITE") loads user roles →
  aggregates permissions JSONB array into set →
  checks required permission in set
```

**Critical edge cases:**

- `expires_at` check in SQL query — never in application code after fetch
- `permissions='*'` wildcard: documented explicit grant — not inferred from empty array
- `AUTH_FAILED` audit log INSERT on every failure (BackgroundTask — never blocks response)

---

### Day 17 — Contract CRUD REST API

**Core objective:** Expose all contract management operations with strict validation,
optimistic locking, and cursor-based pagination (no OFFSET — it's O(n) on large tables).

**Cursor pagination design:**

```python
# Cursor = base64({"created_at": "ISO-timestamp", "id": "uuid"})
# Query: WHERE (created_at, id) < (:cursor_created_at, :cursor_id)
# ORDER BY created_at DESC, id DESC
# Validation: decode cursor, verify both fields are valid types before use
```

**State machine for status transitions:**

```
draft ──► active ──► deprecated
  │                      ▲
  └──────────────────────┘
  (draft → deprecated allowed)
  (deprecated → active: REJECTED — must create new version)
```

**Critical edge cases:**

- `schema_definition` injection: reject keys starting with `__` (e.g. `__proto__`, `constructor`)
- Optimistic locking: `UPDATE ... WHERE updated_at = :expected` — 0 rows → 409 Conflict
- Pagination cursor tampering: base64-decode, validate both field types, reject malformed → 400
- Empty name after strip: `@field_validator('name')` with `str.strip()` + length check

---

### Day 18 — Version Management & VersionCompatibilityChecker

**Core objective:** Enforce semantic versioning correctness at the API level — prevent operators
from publishing breaking schema changes under a MINOR version bump.

**Breaking change categories (8 total):**

| #   | Change                           | Classification   |
| --- | -------------------------------- | ---------------- |
| 1   | Remove required field            | BREAKING (MAJOR) |
| 2   | Change field type                | BREAKING (MAJOR) |
| 3   | Remove enum value                | BREAKING (MAJOR) |
| 4   | Add required field               | BREAKING (MAJOR) |
| 5   | Reduce numeric range             | BREAKING (MAJOR) |
| 6   | Add optional field               | ADDITIVE (MINOR) |
| 7   | Add enum value                   | ADDITIVE (MINOR) |
| 8   | Change description/metadata only | PATCH            |

**Critical edge cases:**

- Version rollback (`v1.0` after `v2.0` active): requires `force=true` flag + audit log entry
- Concurrent activation: `SELECT FOR UPDATE` → exactly 1 succeeds, others get 409
- `enum_values` array ordering: sort both before comparison — `["A","B"]` ≡ `["B","A"]`

---

### Day 19 — GET /api/v1/contracts/active Bundle Endpoint, ETag, 60s App-Level Cache

**Core objective:** This endpoint is called by every SDK client at bootstrap and every TTL
refresh cycle. It must be cheap to serve at high concurrency.

**Thundering herd prevention:**

```python
# Per-(tenant_id, project_id) asyncio.Lock
_cache: dict[tuple, tuple[dict, str, float]] = {}  # → (bundle, etag, expires_at)
_locks: dict[tuple, asyncio.Lock] = {}

async def get_active_bundle(tenant_id: UUID, project_id: UUID) -> tuple[dict, str]:
    key = (tenant_id, project_id)
    async with _locks.setdefault(key, asyncio.Lock()):
        # Only ONE coroutine enters DB fetch; all others await the lock result
        if key in _cache and _cache[key][2] > time.time():
            return _cache[key][0], _cache[key][1]
        bundle = await db.fetch_active_bundle(tenant_id, project_id)
        etag = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
        _cache[key] = (bundle, etag, time.time() + 60)
        return bundle, etag
```

**Response headers:**

```
ETag: "sha256-of-bundle"
Cache-Control: max-age=60, must-revalidate
```

**Critical edge cases:**

- Multi-worker deployment: app-level cache is per-process — documented; Redis cache in Phase 3
- ETag: full `hexdigest(32_bytes)` — no truncation
- Empty project (no active contracts): `{"synced_at": "...", "contracts": []}` → HTTP 200, not 404
- Cache invalidation: `bundle_cache.invalidate(tenant_id, project_id)` called on version activation

---

### Day 20 — JSONB Query Optimisation Audit

**Core objective:** Every query that touches `contracts` or `contract_versions` must use an
index. Zero sequential scans on tables with more than 1,000 rows — verified, not assumed.

**Audit checklist:**

| Query                                                 | Expected plan    | Index used              |
| ----------------------------------------------------- | ---------------- | ----------------------- |
| `WHERE schema_definition @> '{"type":"object"}'`      | Bitmap Heap Scan | `idx_cv_schema_gin`     |
| `WHERE is_active = TRUE AND contract_id = $1`         | Index Scan       | `idx_cv_active`         |
| `WHERE tenant_id = $1 ORDER BY created_at DESC`       | Index Scan       | `idx_contracts_tenant`  |
| `WHERE project_id = $1`                               | Index Scan       | `idx_contracts_project` |
| `telemetry_logs WHERE tenant_id=$1 AND status='fail'` | Bitmap Heap Scan | `idx_tel_status_tenant` |

**Additional indexes for telemetry (added this day):**

```sql
CREATE INDEX idx_tel_tenant_time ON telemetry_logs(tenant_id, created_at DESC);
CREATE INDEX idx_tel_status_tenant ON telemetry_logs(tenant_id, status)
    WHERE status = 'fail';
```

**Critical edge cases:**

- GIN does not support `NOT @>` (negative containment) — document, require rewrite
- Run `ANALYZE` after each migration in CI — without it, cardinality estimates cause wrong plans
- `autovacuum_vacuum_scale_factor = 0.01` for `contract_versions` — frequent `is_active` updates

---

### Day 21 — API Key Auth Guard, Token Bucket Rate Limiting, Middleware Stack Order

**Core objective:** Apply rate limiting that is safe under concurrent requests (asyncio.Lock per
bucket) and correctly ordered in the middleware stack so CORS preflight always passes.

**Token bucket implementation:**

```python
@dataclass
class TokenBucket:
    tokens: float
    last_refill: float
    capacity: int = 1000
    refill_rate: int = 100   # tokens/second

    async def consume(self, n: int = 1) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False
```

**Response headers on every response:**

```
X-RateLimit-Limit:     1000
X-RateLimit-Remaining: 734
X-RateLimit-Reset:     1717200060
Retry-After:           10   (only on 429)
```

**Critical edge cases:**

- CORS **before** rate limiting in stack — OPTIONS preflight must never return 429
- Bucket dict growth: LRU evict after 10,000 unique API keys
- `X-Request-ID` from client: validate as UUID before binding — prevents log injection

---

### Day 22 — RBAC Enforcement, Role Assignment API, audit_logs

**Core objective:** Enforce the principle of least privilege on every endpoint. The permission
check must be a database query result cached at auth time — never N+1 per request.

**Permission constants:**

```python
# apps/telemetry-plane/src/amce_telemetry/auth/permissions.py
CONTRACT_READ    = "contract:read"
CONTRACT_WRITE   = "contract:write"
CONTRACT_PUBLISH = "contract:publish"
TELEMETRY_READ   = "telemetry:read"
ADMIN_ALL        = "*"
```

**Endpoint permission matrix:**

| Endpoint                              | Required permission |
| ------------------------------------- | ------------------- |
| `POST /api/v1/contracts`              | `CONTRACT_WRITE`    |
| `GET  /api/v1/contracts`              | `CONTRACT_READ`     |
| `PATCH /api/v1/contracts/{id}/status` | `CONTRACT_PUBLISH`  |
| `POST /api/v1/telemetry`              | `TELEMETRY_READ`    |

**Critical edge cases:**

- Permission aggregation: 10 roles × 50 permissions = aggregate into set at auth time, not per-request DB
- Circular role inheritance: Phase 1 only supports flat arrays — validate no nested role objects in JSONB
- Role deletion: `ON DELETE CASCADE` on `user_roles.role_id` — no orphaned assignments

---

### Day 23 — POST /api/v1/telemetry (202 Accepted, BackgroundTasks, Kafka Stub, Deduplication)

**Core objective:** Accept telemetry batches at high frequency and return 202 immediately.
The Kafka pipeline is a stub in Phase 1 (mock producer); real Kafka wires up in Phase 2 Day 28.

**Request flow:**

```
POST /api/v1/telemetry
  → validate batch (max 500 events, checked in request validator before BackgroundTask)
  → return HTTP 202 {"accepted": N}  ← response exits here, < 5ms
  ↓ (BackgroundTask runs after response)
  process_telemetry_batch(events, org_id)
  → dedup_check(sha256(tenant+contract+status+duration[:6]+created_at[:13]))
  → TelemetryProducer.publish() [mock in Phase 1, real in Phase 2]
  → on 3× failure → INSERT into telemetry_dlq
```

**Deduplication window:**

```python
# 1-minute granularity, in-process TTL dict (Redis in Phase 3)
dedup_key = sha256(f"{tenant_id}:{contract_id}:{status}:{duration_ms:.6f}:{created_at[:13]}")
```

**Critical edge cases:**

- Batch size validation in the router validator (before BackgroundTask) — prevents memory exhaustion
- Kafka unavailable: all events → DLQ, never silently dropped
- Dedup dict cleanup: APScheduler sweeps entries older than 2 minutes

---

### Day 24 — Phase 1 Sign-Off: 60 Integration Tests, Multi-Tenant Isolation, API p99<100ms

**Core objective:** Verify the control plane under concurrent load and across tenant isolation
boundaries. No cross-tenant data leaks are acceptable.

**Sign-off checklist:**

| Criterion                                  | Target                          | Tool                      |
| ------------------------------------------ | ------------------------------- | ------------------------- |
| Integration test count                     | 60/60 passing                   | pytest                    |
| Multi-tenant isolation                     | 0 leaks across 18 scenarios     | direct DB assertions      |
| API p99 under 100 concurrent users         | < 100ms                         | locust / pytest-benchmark |
| GET /contracts/active with thundering herd | 1 DB fetch for 100 concurrent   | asyncio.Lock verification |
| Rate limit enforcement                     | 429 on request 1001             | pytest                    |
| RBAC enforcement                           | 403 for wrong permission        | pytest                    |
| Audit log completeness                     | entry for every write operation | DB assertion              |

```bash
# Full sign-off run
pytest tests/integration/phase1_suite.py -v --tb=short

# Performance baseline
locust --headless -u 100 -r 10 --run-time 60s \
    --host http://localhost:8000 \
    -f tests/performance/locustfile.py

# Tag
git tag -a v0.1.0-phase1-complete \
    -m "Phase 1: Control Plane. 60/60 tests. p99<100ms. Zero cross-tenant leaks."
```

---

## Dependencies

```toml
# apps/telemetry-plane/pyproject.toml
dependencies = [
  "amce-core-engine",               # workspace dep: Phase 0 SDK
  "fastapi>=0.111",
  "uvicorn[standard]>=0.30",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "pydantic-settings>=2.3",
  "structlog>=24.2",
  "bcrypt>=4.1",
  "httpx>=0.27",
  "packaging>=24.0",                # semver parsing
  "apscheduler>=3.10",              # Phase 2 drift scheduler
]
```

---

## Nx Commands for This Phase

```bash
# Serve with hot reload
nx serve telemetry-plane

# Run migrations
nx migrate telemetry-plane

# Test (unit only)
nx test telemetry-plane

# Test (integration — requires Docker services)
nx test-integration telemetry-plane

# Docker build
nx docker-build telemetry-plane

# Full pre-commit check
nx lint telemetry-plane && nx typecheck telemetry-plane
```

---

## Migration Path: Monolith → Microservices

The monolith splits at the router level. Migration is additive — the monolith continues running
while new services come online behind a path-based API gateway.

```
Step 1: Extract svc-contract-registry
  - Copy: routers/contracts.py, services/contract_repository.py, services/versioning.py
  - Move: alembic migrations 001-002 (identity + contracts schema)
  - Wire:  API gateway routes /api/v1/contracts/* → svc-contract-registry
  - Decom: same routes from telemetry-plane after verification

Step 2: Extract svc-auth-gateway (or promote to libs/amce-auth)
  - Move: auth/api_key_guard.py, auth/rbac.py, auth/permissions.py
  - Deploy as sidecar / shared middleware to all services
  - All services validate token via svc-auth-gateway before handling request

Step 3: Extract svc-telemetry-ingestion
  - Grows significantly in Phase 2 (Kafka, ClickHouse consumer)
  - Move: routers/telemetry.py, consumers/ (Phase 2)
  - Keeps: its own telemetry_dlq table

Shared boundary:
  - amce-core-engine SDK published to internal PyPI
  - Shared PostgreSQL in monolith; per-service schemas in microservices (schema isolation)
  - Internal service-to-service auth via X-Service-Token header (shared secret or mTLS)
```
