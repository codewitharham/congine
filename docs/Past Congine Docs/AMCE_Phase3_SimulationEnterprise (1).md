# AMCE — Phase 3: Simulation Harness & Enterprise Extensions

**Days 35–45 | Gold Set Extraction, Benchmarking Engine, REST Gateway, GDPR Compliance**

---

## Phase Overview

Phase 3 completes the MVP with three enterprise-grade capability domains: a model benchmarking
simulation harness (gold set extraction, parallel async replay, Rc scoring), a language-agnostic
REST validation gateway (the public-facing runtime enforcement API), and compliance
infrastructure (EU/GDPR data residency routing, AES-256-GCM field encryption, GDPR
export/delete/anonymise).

Phase 3 also upgrades the token bucket rate limiter to Redis-backed Lua scripts for atomic
multi-worker correctness, and adds circuit breakers around all external API calls.

**Key deliverables:**

- `GoldSetExtractor` with SimHash diversity filtering from ClickHouse
- `BenchmarkingEngine` with `asyncio.TaskGroup` parallel replay and Rc scoring
- `BenchmarkReport` with field-level divergence heatmap and efficiency-based model recommendation
- `POST /api/v1/gateway/validate` — language-agnostic synchronous validation REST endpoint
- Redis Lua atomic token bucket (multi-worker safe) + circuit breaker for all external calls
- `DataResidencyPolicy` with HTTP 451 routing and ClickHouse region routing
- `GDPRService` — Article 15 export, Article 17 erasure, AES-256-GCM PII encryption
- Security hardening: bandit, safety, OWASP ZAP, 125-entry RBAC matrix, SOC2 evidence
- 80 integration tests, gateway p99 < 50ms at 1,000 req/sec, 375 total tests across all phases
- Final: OpenAPI spec, 5 ADRs, deployment runbook, `v0.1.0-mvp` tag

---

## Architecture Position

```
External callers (any language: Python, Go, Node, Java)
   │
   │  POST /api/v1/gateway/validate
   ▼
┌──────────────────────────────────────────────────────────────────┐
│                   apps/telemetry-plane  (extended)                │
│                                                                  │
│  ── Phase 3 additions ──────────────────────────────────────     │
│                                                                  │
│  routers/gateway.py          ← REST validation gateway          │
│  routers/benchmarks.py       ← benchmark job management         │
│  routers/compliance.py       ← GDPR export/delete               │
│                                                                  │
│  simulation/                                                     │
│    gold_set.py               ← GoldSetExtractor (SimHash)       │
│    benchmarking_engine.py    ← asyncio.TaskGroup parallel replay │
│    model_clients.py          ← OpenAI / Anthropic async clients  │
│    report.py                 ← BenchmarkReport + efficiency Rc   │
│                                                                  │
│  compliance/                                                     │
│    data_residency.py         ← DataResidencyPolicy, 451         │
│    gdpr_service.py           ← export / delete / anonymise      │
│    encryption.py             ← AES-256-GCM field encryption      │
│                                                                  │
│  middleware/rate_limit_redis.py ← Redis Lua atomic bucket       │
│  circuit_breaker.py          ← CLOSED / OPEN / HALF_OPEN        │
└─────────────────────────────┬────────────────────────────────────┘
                              │
             ┌────────────────┼─────────────────┐
             ▼                ▼                 ▼
      Redis (rate limit  ClickHouse        PostgreSQL
       + dedup cache)   (gold set query   (benchmark_runs
                         gold set items    gdpr_audit
                         region-aware)     gold_sets
                                           gold_set_items)
```

---

## Source Tree

### MVP Layout — Monorepo + Monolith

> Phase 3 adds four new top-level subdirectories inside `amce_telemetry` and a new library
> (`libs/benchmark-engine`). The simulation harness is a separate library because it will be
> independently published and independently consumed by multiple future services.

```
amce-monorepo/
│
├── libs/
│   ├── amce-core-engine/              ← unchanged (Phase 0)
│   │
│   └── benchmark-engine/              ← NEW in Phase 3
│       ├── project.json               ← Nx: test, build, security-scan
│       ├── pyproject.toml             ← hatchling, uv workspace member
│       │
│       └── src/
│           └── amce_benchmark/
│               ├── __init__.py        ← public API: GoldSetExtractor,
│               │                         BenchmarkingEngine, BenchmarkReport
│               │
│               │   ── Gold Set Domain ──
│               ├── extractors/
│               │   ├── __init__.py
│               │   └── gold_set.py    ← GoldSetExtractor:
│               │                         extract(tenant_id, contract_id, max_size, min_diversity)
│               │                         SimHash 64-bit fingerprints
│               │                         Hamming distance diversity filter
│               │                         GoldSet + GoldSetItem models
│               │
│               │   ── Simulation Engine ──
│               ├── engines/
│               │   ├── __init__.py
│               │   ├── benchmarking.py  ← BenchmarkingEngine:
│               │   │                       run(config) → BenchmarkReport
│               │   │                       asyncio.TaskGroup parallel replay
│               │   │                       asyncio.Semaphore(max_concurrency=50)
│               │   │                       global timeout: asyncio.wait_for(..., 3600)
│               │   └── model_clients.py ← factory: AsyncOpenAI / AsyncAnthropic
│               │                          API key from env var (never stored in config)
│               │
│               │   ── Reporting ──
│               ├── reporting/
│               │   ├── __init__.py
│               │   └── report.py      ← BenchmarkReport, ModelResult DTO:
│               │                         Rc = pass_count / gold_set_size
│               │                         efficiency_score = Rc / max(cost_usd, 0.0001)
│               │                         field_divergence_heatmap
│               │                         recommended_model (argmax efficiency, Rc > 0.7)
│               │
│               │   ── Graph / Mutation (Phase 4 stub) ──
│               └── mutators/
│                   ├── __init__.py
│                   └── contract_mutator.py  ← future: schema mutation for adversarial testing
│
│       └── tests/
│           ├── unit/
│           │   ├── test_gold_set.py       ← Day 35: SimHash, diversity, size cap
│           │   ├── test_benchmarking.py   ← Day 36–37: cost estimate, Rc, TaskGroup isolation
│           │   └── test_report.py         ← Day 38: efficiency score, recommendation logic
│           └── integration/
│               └── test_benchmark_e2e.py  ← Day 38: full benchmark job API lifecycle
│
│
├── apps/
│   └── telemetry-plane/
│       ├── alembic/
│       │   └── versions/
│       │       ├── ...                    (Phases 1–2 migrations)
│       │       ├── 008_gold_sets.py       ← Day 35: gold_sets + gold_set_items
│       │       ├── 009_benchmark_runs.py  ← Day 38: benchmark_runs table
│       │       └── 010_data_boundary.py   ← Day 41: data_boundary_events audit
│       │
│       └── src/
│           └── amce_telemetry/
│               │   (all Phase 1–2 files unchanged)
│               │
│               │   ── Simulation Integration (uses libs/benchmark-engine) ──
│               ├── simulation/
│               │   ├── __init__.py
│               │   └── job_manager.py     ← BenchmarkJobManager:
│               │                             POST /benchmarks → launch BackgroundTask
│               │                             GET  /benchmarks/{id} → poll status
│               │                             per-tenant asyncio.Semaphore (max 3 concurrent)
│               │                             store result in benchmark_runs table
│               │
│               │   ── Compliance Domain ──
│               ├── compliance/
│               │   ├── __init__.py
│               │   ├── data_residency.py  ← DataResidencyPolicy:
│               │   │                         get_policy(tenant_id) → ResidencyPolicy
│               │   │                         route_request() → RoutingDecision
│               │   │                         HTTP 451 on cross-region violation
│               │   │                         ClickHouse region-aware connection pool
│               │   │                         data_boundary_events audit INSERT
│               │   ├── gdpr_service.py    ← GDPRService:
│               │   │                         export_data() → streaming ZIP archive
│               │   │                         delete_data() → DeletionCertificate
│               │   │                         anonymise_field() per type (email/name/IP)
│               │   │                         ClickHouse async mutation poll
│               │   └── encryption.py      ← AES-256-GCM EncryptedField:
│               │                             encrypt(value, tenant_key)
│               │                             decrypt(ciphertext, tenant_key)
│               │                             os.urandom(12) nonce per operation
│               │                             AWS Secrets Manager key fetcher (mock in dev)
│               │
│               │   ── REST Validation Gateway ──
│               ├── routers/
│               │   ├── ...                (Phase 1–2 routers unchanged)
│               │   ├── gateway.py         ← POST /api/v1/gateway/validate
│               │   │                         synchronous: load schema → validate → respond
│               │   │                         1MB body limit, 10-level nesting limit
│               │   │                         separate rate bucket (gateway tier)
│               │   │                         emit_telemetry=true → BackgroundTask publish
│               │   ├── benchmarks.py      ← POST /api/v1/benchmarks (launch)
│               │   │                         GET  /api/v1/benchmarks/{id} (poll)
│               │   └── compliance.py      ← POST /api/v1/gdpr/export
│               │                             DELETE /api/v1/gdpr/users/{id}
│               │
│               │   ── Upgraded Infrastructure ──
│               ├── middleware/
│               │   ├── ...
│               │   └── rate_limit_redis.py  ← Redis Lua atomic token bucket
│               │                               replaces in-process rate_limit.py
│               │                               Lua script: check-and-decrement atomic
│               │                               KEYS[1]=bucket_key, ARGV[1]=capacity, ...
│               │
│               └── circuit_breaker.py     ← CircuitBreaker(CLOSED/OPEN/HALF_OPEN):
│                                             failure_threshold=5
│                                             recovery_timeout_seconds=60
│                                             asyncio.Lock on HALF_OPEN probe
│                                             wired: TelemetryProducer + model API calls
│
└── docs/
    ├── adr/
    │   ├── ADR-001-lfu-cache-over-redis.md
    │   ├── ADR-002-jsonb-over-schema-table.md
    │   ├── ADR-003-kafka-over-direct-clickhouse.md
    │   ├── ADR-004-bfs-cte-over-neo4j.md
    │   └── ADR-005-fail-closed-default.md
    ├── soc2/
    │   ├── CC6.1-access-control.md
    │   ├── CC6.7-transmission-security.md
    │   ├── CC7.2-incident-management.md
    │   └── CC8.1-change-management.md
    ├── indexes.md                 ← all DB indexes with query plan evidence
    ├── runbook.md                 ← deployment, migration, rollback procedures
    ├── security_audit.md          ← bandit + safety + ZAP findings
    └── performance_baseline.md   ← machine spec + p50/p95/p99 numbers
```

### Future Microservice Extraction Path

> Phase 3 adds the two remaining services that will complete the microservices topology.

```
[MVP]  apps/telemetry-plane (monolith)
         ├── simulation/        ──────→ [MSvc] svc-simulation-harness
         │   └── job_manager.py           uses: libs/benchmark-engine (internal PyPI)
         │                                owns: benchmark_runs, gold_sets tables
         │                                calls: svc-contract-registry (schema fetch)
         │                                calls: ClickHouse (gold set extraction)
         │                                scales: GPU workers for embedding calls
         │
         ├── compliance/        ──────→ [MSvc] svc-compliance
         │   ├── gdpr_service.py          owns: data_boundary_events, audit tables
         │   └── data_residency.py        enforces: region routing for ALL services
         │                                scales: CPU-light; 1 replica sufficient
         │
         └── routers/gateway.py ──────→ [MSvc] svc-validation-gateway
                                          uses: amce-core-engine (internal PyPI)
                                          calls: svc-contract-registry (cache warm)
                                          owns: NO persistent state (stateless)
                                          scales: horizontal; 10K+ RPS per replica

# libs/benchmark-engine extraction:
#   Published to internal PyPI as amce-benchmark-engine==x.y.z
#   Consumed by svc-simulation-harness
#   NOT consumed by the validation hot path (simulation is async, gateway is sync)

# Final microservices topology (post Phase 3):
#
#   svc-auth-gateway          → API key validation, RBAC
#   svc-contract-registry     → contracts CRUD, versioning, bundle endpoint
#   svc-validation-gateway    → POST /gateway/validate (stateless, scales to 10K RPS)
#   svc-telemetry-ingestion   → Kafka producer + consumer + ClickHouse
#   svc-graph-analytics       → BFS engine, blast radius
#   svc-analytics-engine      → drift, SLA, volume monitor
#   svc-simulation-harness    → gold set + benchmarking engine
#   svc-compliance            → GDPR + data residency
#
#   Shared libs (internal PyPI):
#     amce-core-engine        → used by: gateway, contract-registry, simulation
#     amce-benchmark-engine   → used by: simulation-harness
```

---

## Database Schema

### Migration 008 — Gold Sets (Day 35)

```sql
CREATE TABLE gold_sets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    contract_id UUID NOT NULL REFERENCES contracts(id),
    size        INTEGER NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE gold_set_items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gold_set_id             UUID NOT NULL REFERENCES gold_sets(id) ON DELETE CASCADE,
    input_hash              VARCHAR(64) NOT NULL,
    structural_snapshot     JSONB NOT NULL,
    selected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_gsi_gold_set ON gold_set_items(gold_set_id);
```

### Migration 009 — Benchmark Runs (Day 38)

```sql
CREATE TABLE benchmark_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    contract_id     UUID NOT NULL,
    gold_set_id     UUID REFERENCES gold_sets(id),
    status          VARCHAR(50) NOT NULL DEFAULT 'RUNNING'
                    CHECK(status IN ('RUNNING','COMPLETE','FAILED')),
    report_json     JSONB,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error_message   TEXT
);
CREATE INDEX idx_benchmark_runs_tenant ON benchmark_runs(tenant_id, started_at DESC);
```

---

## Day-by-Day Implementation Plan

### Day 35 — GoldSetExtractor: SimHash Diversity Filtering, gold_sets Table

**Core objective:** Extract a maximally diverse sample of real production inputs from ClickHouse
to use as the benchmark gold set. SimHash ensures no two test inputs are structurally identical.

**Files created:**

- `libs/benchmark-engine/src/amce_benchmark/extractors/gold_set.py`
- `apps/telemetry-plane/alembic/versions/008_gold_sets.py`

**SimHash algorithm:**

```python
def simhash_64(obj: dict) -> int:
    """64-bit SimHash of a JSON object's structural content."""
    tokens = _bigrams(json.dumps(obj, sort_keys=True))  # sort for determinism
    vector = [0] * 64
    for token in tokens:
        h = hashlib.md5(token.encode()).digest()[:8]     # 64-bit hash
        bits = int.from_bytes(h, 'big')
        for i in range(64):
            vector[i] += 1 if (bits >> i) & 1 else -1
    return sum(1 << i for i in range(64) if vector[i] > 0)

def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count('1')
```

**Diversity selection:**

```python
selected = []
for candidate in candidates:
    fp = simhash_64(candidate.structural_snapshot)
    if all(hamming_distance(fp, s.fingerprint) >= min_dist for s in selected):
        selected.append(GoldSetItem(fingerprint=fp, ...))
    if len(selected) >= max_size:
        break
```

**Critical edge cases:**

- SimHash on < 4 bigrams: unconditionally include (too few tokens for stable fingerprint)
- Empty ClickHouse result: return `GoldSet(size=0, items=[])` — never raise
- `input_hash` collision: `DISTINCT input_hash` in SQL query handles this correctly
- Stratified sampling flag: `sample by toYYYYMMDD(created_at)` for temporal diversity

**Verification:**

```bash
# 5,000 events → diversity filter → no two items within Hamming distance 3
pytest libs/benchmark-engine/tests/unit/test_gold_set.py::test_diversity_filter -v

# max_size=50 from 1,000 diverse candidates → exactly 50 items returned
pytest libs/benchmark-engine/tests/unit/test_gold_set.py::test_size_capping -v

# SimHash determinism: same input → same fingerprint across calls
pytest libs/benchmark-engine/tests/unit/test_gold_set.py::test_simhash_determinism -v
```

---

### Day 36 — BenchmarkingEngine Scaffold: BenchmarkConfig, ModelConfig, Cost Estimation, Semaphore

**Core objective:** Define the benchmarking data model and build the cost estimation layer.
An operator should know the financial cost of a benchmark before running it.

**Files created:**

- `libs/benchmark-engine/src/amce_benchmark/engines/benchmarking.py`
- `libs/benchmark-engine/src/amce_benchmark/engines/model_clients.py`

**BenchmarkConfig model:**

```python
class ModelConfig(BaseModel, frozen=True):
    provider:                  str       # 'openai' | 'anthropic'
    model_id:                  str       # e.g. 'gpt-4o-mini'
    api_key_env:               str       # env var name — never the key itself
    temperature:               float = 0.0
    max_tokens:                int   = 1000
    cost_per_1k_tokens_input:  float     # USD
    cost_per_1k_tokens_output: float     # USD

class BenchmarkConfig(BaseModel, frozen=True):
    gold_set:          GoldSet
    candidate_models:  list[ModelConfig]
    base_model:        ModelConfig
    max_concurrency:   int = 50
    timeout_ms:        int = 30000
```

**Cost estimation:**

```python
def estimate_cost(config: BenchmarkConfig) -> CostEstimate:
    per_model = {}
    for model in config.candidate_models:
        est_tokens = avg_input_tokens * config.gold_set.size
        cost = (est_tokens / 1000) * model.cost_per_1k_tokens_input
        per_model[model.model_id] = cost
    return CostEstimate(
        per_model=per_model,
        total_usd=sum(per_model.values()),
        accuracy='ESTIMATE_PLUS_MINUS_50PCT'  # honest disclaimer
    )
```

**Critical edge cases:**

- `api_key_env` is the env var **name** — fetch via `os.environ.get(config.api_key_env)` at runtime
- Missing env var: raise `BenchmarkConfigError` **before** any API calls start
- Global timeout: `asyncio.wait_for(run_all_benchmarks(), timeout=3600)` — 1-hour hard cap
- Semaphore starvation: all 50 slots held by slow requests → global timeout saves it

---

### Day 37 — Parallel Async Replay with asyncio.TaskGroup, Rc Score, Field-Level Divergence

**Core objective:** Execute the benchmark with maximum parallelism while isolating individual
task failures. A single model API error must never abort the entire benchmark run.

**Files created:**

- `libs/benchmark-engine/src/amce_benchmark/engines/benchmarking.py` (continued)

**TaskGroup with per-task exception isolation:**

```python
async def run(self, config: BenchmarkConfig) -> BenchmarkReport:
    results: dict[str, list[ModelRunResult]] = defaultdict(list)

    async with asyncio.TaskGroup() as tg:
        for model in config.candidate_models:
            for item in config.gold_set.items:
                tg.create_task(
                    self._safe_run_one(model, item, results)  # try/except inside
                )
    return self._aggregate(results, config)

async def _safe_run_one(self, model, item, results):
    try:
        async with self._semaphore:
            raw = await asyncio.wait_for(
                self._call_model(model, item.input_prompt),
                timeout=self.config.timeout_ms / 1000
            )
        result = self._validate(raw, model)
    except Exception as e:
        result = ModelRunResult(status='error', error=str(e))  # never re-raise
    results[model.model_id].append(result)
```

**Rc formula:**

```
Rc = count(status == 'pass') / len(gold_set.items)
```

**Field-level divergence formulas:**

| Field type          | Formula                                                    |
| ------------------- | ---------------------------------------------------------- |
| Enum / string exact | `1.0` if mismatch, `0.0` if match                          |
| Numeric             | `abs(base_val - cand_val) / max(range_max - range_min, 1)` |
| Text (embedding)    | `1.0 - cosine_similarity(embed(base), embed(candidate))`   |

**Critical edge cases:**

- `asyncio.TaskGroup` cancels all tasks on unhandled exception: wrap each task in `_safe_run_one`
- Base model timeout: divergence `= None` for all fields on that item (no partial divergence)
- Embedding batching: call `model.encode(all_texts_for_model)` once per model, not per field
- `Rc=0.0` all errors: flag as `potentially_unreliable=True` in report

---

### Day 38 — Benchmark Report API, ModelResult DTO, RecommendedModel, Field Heatmap

**Core objective:** Expose the benchmark results via API with a clear model recommendation
signal — the primary output that operators use to make model selection decisions.

**Files created:**

- `libs/benchmark-engine/src/amce_benchmark/reporting/report.py`
- `apps/telemetry-plane/src/amce_telemetry/routers/benchmarks.py`
- `apps/telemetry-plane/src/amce_telemetry/simulation/job_manager.py`
- `apps/telemetry-plane/alembic/versions/009_benchmark_runs.py`

**Efficiency score formula:**

```
efficiency_score_raw  = Rc / max(total_cost_usd, 0.0001)   # cap prevents ÷0
efficiency_score_norm = score_raw / max(all_candidates_raw) # normalise to [0,1]
```

**Recommendation logic:**

```python
eligible = [m for m in candidates if m.rc_score >= 0.70]
if not eligible:
    recommended = None   # never recommend below quality threshold
else:
    recommended = max(eligible, key=lambda m: m.efficiency_score)
```

**Poll-based async pattern:**

```
POST /api/v1/benchmarks → {benchmark_id, status: 'RUNNING'}  HTTP 202
GET  /api/v1/benchmarks/{id} → {status: 'RUNNING'}           (poll)
GET  /api/v1/benchmarks/{id} → {status: 'COMPLETE', report}  (done)
```

**Critical edge cases:**

- Long-running benchmark (500 LLM calls): HTTP must not stay open — BackgroundTask mandatory
- Zero-cost model (`cost=0`, open-source): `max(cost, 0.0001)` prevents infinity
- Max 3 concurrent benchmark runs per tenant: `dict[tenant_id, asyncio.Semaphore(3)]`
- `recommended=None` with message `'No candidate meets minimum Rc threshold of 0.70'`

---

### Day 39 — REST Validation Gateway (POST /api/v1/gateway/validate), Language-Agnostic

**Core objective:** Provide a language-agnostic synchronous validation endpoint. Any system
that can make an HTTP request can enforce an AMCE contract — no SDK installation required.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/routers/gateway.py`

**Request/Response:**

```python
class GatewayValidationRequest(BaseModel):
    contract_id:     str
    version:         str  = 'active'
    payload:         dict
    emit_telemetry:  bool = True
    timeout_ms:      int  = 5000

class GatewayValidationResponse(BaseModel):
    status:      Literal['pass', 'fail', 'timeout']
    duration_ms: float
    breaches:    list[dict] | None
    contract_id: str
    version:     str
```

**Request flow (synchronous — awaits result):**

```
1. Extract tenant from API key (ApiKeyGuard)
2. Load schema from LFU cache (AmceClient.get_schema())
   → cache miss: synchronous reload, never 404
3. Run LocalValidator.validate(payload, schema)
4. Return GatewayValidationResponse    ← response exits here
5. (BackgroundTask) if emit_telemetry: publish TelemetryEvent to Kafka
```

**Payload safety guards:**

```python
# 1MB body limit
if len(await request.body()) > 1_048_576:
    raise HTTPException(413, "Payload exceeds 1MB limit")

# 10-level nesting depth
if _max_depth(payload) > 10:
    raise HTTPException(422, "Payload nesting depth exceeds maximum of 10 levels")

# timeout_ms clamping
timeout_ms = max(100, request.timeout_ms)   # minimum 100ms regardless of input
```

**Gateway-specific rate bucket:** separate `TokenBucket` from contract management endpoints
— gateway may be called at 1,000+ req/sec; management endpoints at <1 req/sec

**Critical edge cases:**

- Cache miss on `contract_id`: synchronous reload (one-time penalty), never 404
- Deep nesting attack: `_max_depth()` recursive function with `limit=10` short-circuit
- `emit_telemetry=False`: skip BackgroundTask entirely — no Kafka publish, faster response

---

### Day 40 — Redis Lua Atomic Token Bucket, Circuit Breaker, Payload Depth Limiter

**Core objective:** Upgrade rate limiting to Redis for multi-worker correctness. Add circuit
breakers so that external API failures (Kafka, LLM APIs) fail fast rather than accumulating
blocked threads.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/middleware/rate_limit_redis.py`
- `apps/telemetry-plane/src/amce_telemetry/circuit_breaker.py`

**Redis Lua script (atomic check-and-decrement):**

```lua
-- KEYS[1] = bucket key
-- ARGV[1] = capacity, ARGV[2] = refill_rate (tokens/sec), ARGV[3] = now_seconds
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens     = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * rate)
last_refill = now

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', key, 3600)
    return {1, math.floor(tokens), math.floor(now + (1 - tokens) / rate)}
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    return {0, 0, math.floor(now + (1 - tokens) / rate)}
end
```

**Circuit Breaker state machine:**

```
CLOSED ──[5 failures]──► OPEN ──[60s timeout]──► HALF_OPEN
  ▲                                                    │
  └────────────[1 success probe]─────────────────────-┘

In OPEN state: raise CircuitOpenException immediately (no attempt)
In HALF_OPEN:  asyncio.Lock ensures exactly ONE probe request at a time
```

**Wired to:**

- `TelemetryProducer.publish()` — Kafka failures
- `BenchmarkingEngine._call_model()` — LLM API failures
- `ClickHouseClient.bulk_insert()` — ClickHouse failures

**Critical edge cases:**

- Lua script in Redis cluster mode: must use `KEYS[1]` for correct slot assignment
- HALF_OPEN `asyncio.Lock`: prevents multiple simultaneous probes from all succeeding
- Redis connection pool: `aioredis pool_size=20`, log WARNING at > 80% utilisation

---

### Day 41 — DataResidencyPolicy, EU/GDPR Region Routing, HTTP 451, ClickHouse Region Routing

**Core objective:** Implement hard data residency boundaries. EU tenant data must never touch
a US ClickHouse cluster — this is a GDPR compliance requirement, not a preference.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/compliance/data_residency.py`
- `apps/telemetry-plane/alembic/versions/010_data_boundary.py`

**Routing decision flow:**

```python
class DataResidencyPolicy:
    def route_request(self, tenant_id: UUID, target_region: str) -> RoutingDecision:
        policy = self.get_policy(tenant_id)
        if policy.region == 'EU' and target_region == 'US':
            return RoutingDecision(
                allowed=False,
                reason='EU_DATA_RESIDENCY',
                status_code=451,
                regulation='GDPR'
            )
        return RoutingDecision(allowed=True)
```

**HTTP 451 response:**

```json
{
  "error": "DATA_RESIDENCY_VIOLATION",
  "tenant_region": "EU",
  "requested_region": "US",
  "regulation": "GDPR"
}
```

Response headers: `Cache-Control: no-store` — never cache a residency policy error

**ClickHouse dual-region routing:**

```python
# infrastructure/clickhouse_client.py
_pools = {
    'US': ClickHousePool(host=settings.CH_US_HOST),
    'EU': ClickHousePool(host=settings.CH_EU_HOST),
}

def get_client(self, tenant_id: UUID) -> ClickHouseClient:
    region = self._residency_policy.get_policy(tenant_id).region
    return _pools[region]  # EU tenants ALWAYS go to EU cluster, never fallback to US
```

**Critical edge cases:**

- `NULL` region in organizations: treat as `'US'`, log WARNING for data backfill
- EU cluster unavailable: EU tenant telemetry MUST fail (no US fallback) — DLQ to EU-local storage only
- 451 response headers: `Cache-Control: no-store` — CDN must not cache this

---

### Day 42 — GDPRService: Export, Delete, Anonymise, AES-256-GCM PII Encryption

**Core objective:** Implement Articles 15 (access), 17 (erasure), and 4(5) (pseudonymisation)
of GDPR. The DeletionCertificate is a legally auditable record retained for 7 years.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/compliance/gdpr_service.py`
- `apps/telemetry-plane/src/amce_telemetry/compliance/encryption.py`

**AES-256-GCM encryption (nonce-per-operation, critical for security):**

```python
def encrypt(self, plaintext: str, tenant_key: bytes) -> str:
    nonce = os.urandom(12)          # MUST be fresh per operation — reuse is catastrophic
    cipher = AESGCM(tenant_key)
    ciphertext = cipher.encrypt(nonce, plaintext.encode(), None)
    return f"{base64.b64encode(nonce).decode()}:{base64.b64encode(ciphertext).decode()}"

def decrypt(self, token: str, tenant_key: bytes) -> str:
    nonce_b64, ct_b64 = token.split(':')
    cipher = AESGCM(tenant_key)
    return cipher.decrypt(base64.b64decode(nonce_b64),
                          base64.b64decode(ct_b64), None).decode()
    # Raises InvalidTag on wrong key — never returns partial plaintext
```

**Anonymisation rules:**

| Field type     | Anonymised form                     |
| -------------- | ----------------------------------- |
| Email          | `anon_{sha256[:8]}@deleted.amce.io` |
| Name           | `ANONYMISED`                        |
| IP address     | Zero last octet: `203.0.113.0`      |
| UUID (user_id) | Replace with new random UUID        |

**ClickHouse deletion (asynchronous mutation):**

```python
# Trigger deletion
mutation_id = await ch_client.execute(
    f"ALTER TABLE amce.telemetry_events DELETE WHERE tenant_id = '{tenant_id}'"
)
# Poll until complete (up to 30 minutes)
while True:
    done = await ch_client.execute(
        f"SELECT is_done FROM system.mutations WHERE mutation_id = '{mutation_id}'"
    )
    if done[0]['is_done'] == 1:
        break
    await asyncio.sleep(10)
```

**DeletionCertificate model:**

```python
class DeletionCertificate(BaseModel, frozen=True):
    tenant_id:              UUID
    user_id:                UUID
    deleted_tables:         list[str]
    deleted_rows:           int
    clickhouse_mutation_id: str
    certified_at:           datetime
    expiry_at:              datetime    # certified_at + 7 years (GDPR audit retention)
```

**Critical edge cases:**

- Export ZIP streaming: use `zipfile.ZipFile` with `compression=ZIP_DEFLATED`, chunk writes — never fully materialise in memory
- AES-GCM nonce reuse: `os.urandom(12)` per call — this is the only safe pattern
- GDPR impersonation: verify `user_id` belongs to requesting `org_id` before any deletion
- ClickHouse mutation timeout: include `mutation_id` in certificate for manual verification at 30-minute timeout

---

### Day 43 — Full System Integration: 80 Tests, Security Audit, Performance Baseline, Grafana Dashboards

**Core objective:** Verify the complete system and document the security posture. Every check
in the security audit checklist must be green before the phase sign-off.

**Files created:**

- `apps/telemetry-plane/tests/integration/phase3_suite.py`
- `docs/security_audit.md`
- `docs/performance_baseline.md`
- `docker/grafana/dashboards/amce-overview.json`

**Grafana dashboard metrics (via OpenTelemetry):**

| Panel                  | Metric                                | Alert threshold |
| ---------------------- | ------------------------------------- | --------------- |
| Validation throughput  | `amce_validations_per_second`         | < 100/s         |
| Gateway p99 latency    | `amce_gateway_p99_ms`                 | > 50ms          |
| Kafka consumer lag     | `amce_kafka_consumer_lag`             | > 5,000 events  |
| ClickHouse insert rate | `amce_clickhouse_insert_rows_per_sec` | < 100/s         |
| Cache hit rate         | `amce_cache_hit_rate`                 | < 85%           |
| Circuit breaker state  | `amce_circuit_breaker_state`          | OPEN (any)      |

**Security audit checklist (`docs/security_audit.md`):**

| Check           | Tool                                              | Status |
| --------------- | ------------------------------------------------- | ------ |
| SQL injection   | Parameterised queries in all repos                | ✓      |
| XSS             | `Content-Type: application/json` on all responses | ✓      |
| SSRF            | No user-controlled URLs fetched server-side       | ✓      |
| Secrets in logs | `grep -r 'api_key\|password' logs/`               | ✓      |
| Rate limiting   | Token bucket on all public endpoints              | ✓      |
| CORS wildcard   | No `*` in production CORS config                  | ✓      |

**Performance target:**

```
1,000 SDK validations/second sustained for 60 seconds
  → gateway p50  < 20ms
  → gateway p95  < 40ms
  → gateway p99  < 50ms
```

---

### Day 44 — Security Hardening: bandit, safety, OWASP ZAP, 125-Entry RBAC Matrix, SOC2 Evidence

**Core objective:** Pass all automated security scans and produce the SOC2 evidence package
required for enterprise sales. The RBAC matrix is also the ground truth for permission testing.

**Files created:**

- `docs/soc2/CC6.1-access-control.md`
- `docs/soc2/CC6.7-transmission-security.md`
- `docs/soc2/CC7.2-incident-management.md`
- `docs/soc2/CC8.1-change-management.md`
- `.github/workflows/security.yml`

**RBAC matrix structure (25 endpoints × 5 roles = 125 entries):**

| Endpoint                         | viewer | developer | publisher | admin | super_admin |
| -------------------------------- | ------ | --------- | --------- | ----- | ----------- |
| `GET /api/v1/contracts`          | ✓      | ✓         | ✓         | ✓     | ✓           |
| `POST /api/v1/contracts`         | ✗      | ✓         | ✓         | ✓     | ✓           |
| `PATCH .../status`               | ✗      | ✗         | ✓         | ✓     | ✓           |
| `POST /api/v1/gateway/validate`  | ✓      | ✓         | ✓         | ✓     | ✓           |
| `DELETE /api/v1/gdpr/users/{id}` | ✗      | ✗         | ✗         | ✓     | ✓           |
| ... (all 25 endpoints)           |        |           |           |       |             |

**CI security gates (`.github/workflows/security.yml`):**

```yaml
- name: Bandit scan
  run: uv run bandit -r libs/ apps/ -f json -o bandit-report.json
  # Fail PR on any HIGH severity finding

- name: Safety check
  run: uv run safety check --json
  # Fail PR on any CVE with CVSS >= 7.0
```

**Critical edge cases:**

- bandit `B101` (assert statements): skip in `tests/` only — never in production code
- ZAP authentication: configure with test API key before active scan; verify it reaches `/api/v1/contracts`
- SOC2 evidence currency: each artifact must be dated within the last 30 days

---

### Day 45 — Final Sign-Off: OpenAPI, SDK Docs, 5 ADRs, Deployment Runbook, 375-Test Suite, v0.1.0-mvp

**Core objective:** Ship the complete MVP with all documentation, tests, and artifacts required
for production deployment and enterprise customer onboarding.

**Files created / finalised:**

- `openapi.json` — auto-generated from FastAPI app
- `docs/adr/ADR-001` through `ADR-005`
- `docs/runbook.md` — executable deployment guide
- `CHANGELOG.md` — full 45-day change log

**OpenAPI export:**

```bash
cd apps/telemetry-plane
python -c '
import json
from amce_telemetry.main import app
spec = app.openapi()
print(f"Documenting {len(spec[\"paths\"])} endpoints")
with open("../../openapi.json", "w") as f:
    json.dump(spec, f, indent=2)
'
# Expected: Documenting >= 20 endpoints
```

**SDK documentation:**

```bash
uv run pdoc --html libs/amce-core-engine/src/amce_core \
    --output-dir docs/sdk/
```

**Runbook sections:**

1. Environment variables — all `AMCE_*`, `DATABASE_URL`, `KAFKA_*`, `CLICKHOUSE_*`, `REDIS_URL`
2. First deployment — `make docker-up`, `make migrate`, `make serve-api`
3. Kafka topic setup — `python infrastructure/kafka/setup.py`
4. ClickHouse DDL — `python infrastructure/clickhouse/setup.py`
5. Health check verification — `curl /health`, `curl /health/deep`
6. Rollback procedure — `alembic downgrade -1`, redeploy prior Docker tag

**Final test count verification:**

```bash
pytest --collect-only 2>&1 | tail -3
# Expected: >= 375 tests collected

# Full suite run (allow ~15 minutes)
pytest libs/ apps/ -v --tb=short --cov=libs --cov=apps \
    --cov-report=html:coverage-report/

# Tag
git tag -a v0.1.0-mvp \
    -m "AMCE MVP v0.1.0: All 375 tests passing. Production-ready."
git push origin v0.1.0-mvp
```

**Final sign-off checklist:**

| Criterion               | Target                       |
| ----------------------- | ---------------------------- |
| Total tests             | ≥ 375 passing                |
| Phase 0 tests           | 50/50                        |
| Phase 1 tests           | 60/60                        |
| Phase 2 tests           | 55/55                        |
| Phase 3 tests           | 80/80                        |
| ADRs                    | 5 written, immutable         |
| OpenAPI endpoints       | ≥ 20 documented              |
| Gateway p99             | < 50ms at 1K req/sec         |
| bandit HIGH findings    | 0                            |
| unfixed CVEs CVSS ≥ 7.0 | 0                            |
| Cross-tenant data leaks | 0                            |
| GDPR deletion verified  | ClickHouse mutation complete |
| Runbook dry-run         | Completed by second engineer |

---

## Dependencies Added in Phase 3

```toml
# libs/benchmark-engine/pyproject.toml
dependencies = [
  "amce-core-engine",
  "pydantic>=2.7",
  "openai>=1.30",
  "anthropic>=0.28",
  "scipy>=1.13",
  "numpy>=2.0",
  "sentence-transformers>=3.0",
  "structlog>=24.2",
]

# Additions to apps/telemetry-plane/pyproject.toml
"amce-benchmark-engine",        # workspace dep: libs/benchmark-engine
"redis>=5.0",                   # aioredis-compatible async client
"cryptography>=42.0",           # AES-256-GCM (AESGCM from cryptography.hazmat)
"boto3>=1.34",                  # AWS Secrets Manager (mock in dev)
"apscheduler>=3.10",            # already added Phase 2
```

---

## Nx Commands for This Phase

```bash
# Test benchmark-engine library
nx test benchmark-engine
nx test-integration benchmark-engine

# Security scan across both libs
nx security-scan amce-core-engine
nx security-scan benchmark-engine

# Build both library wheels
nx build amce-core-engine
nx build benchmark-engine

# Full 375-test suite
nx run-many --target=test --all
nx run-many --target=test-integration --all   # requires Docker services

# Generate OpenAPI spec
nx run telemetry-plane:openapi-export

# Final tag
nx run telemetry-plane:tag-mvp
```

---

## Migration Path: Monolith → Full Microservices

This is the complete microservices extraction roadmap that Phase 3 makes possible.

```
Priority 1 — Extract svc-validation-gateway (STATELESS — easiest)
  Files:    routers/gateway.py + AmceClient (from amce-core-engine)
  Blocker:  needs svc-contract-registry URL for schema fetch
  Scaling:  10K+ RPS per replica, horizontal scale freely
  Timeline: 2 weeks after Phase 3 sign-off

Priority 2 — Extract svc-telemetry-ingestion (ALREADY PROCESS-ISOLATED)
  Files:    consumers/ already runs as separate process
  Action:   promote to separate Docker image + Kubernetes Deployment
  Scaling:  Kafka partitions (12) = max 12 consumer replicas
  Timeline: 1 sprint — mostly DevOps work, minimal code change

Priority 3 — Extract svc-contract-registry
  Files:    routers/contracts.py, services/contract_repository.py,
            services/versioning.py, services/bundle_cache.py
  Blocker:  requires API gateway for svc-to-svc auth
  Scaling:  Read replicas for GET /contracts/active (SDK bootstrap hot path)
  Timeline: 1 sprint

Priority 4 — Extract svc-graph-analytics
  Files:    graph/ module + migration 005
  Blocker:  none (reads its own PostgreSQL schema)
  Scaling:  Read replicas for large tenant graphs
  Timeline: 1 sprint

Priority 5 — Extract svc-analytics-engine
  Files:    analytics/ module (drift, SLA, volume)
  Blocker:  needs ClickHouse read access (shared)
  Scaling:  APScheduler workers scale by number of active contracts
  Timeline: 1 sprint

Priority 6 — Extract svc-simulation-harness
  Files:    simulation/ + libs/benchmark-engine
  Blocker:  GPU workers needed for embedding computation
  Scaling:  GPU instances on-demand (expensive — ephemeral)
  Timeline: 2 sprints

Priority 7 — Extract svc-compliance (LAST — cross-cutting)
  Files:    compliance/ module
  Blocker:  needs access to ALL other services' data for export
  Design:   data export becomes async job aggregating from all services
  Timeline: 1 quarter

Shared infrastructure (never extracted to a service):
  libs/amce-core-engine    → internal PyPI package
  libs/benchmark-engine    → internal PyPI package
  PostgreSQL               → managed RDS, per-service schema namespaces
  Kafka                    → managed MSK, shared cluster
  ClickHouse               → managed ClickHouse Cloud, region-separated
  Redis                    → managed ElastiCache, shared
```
