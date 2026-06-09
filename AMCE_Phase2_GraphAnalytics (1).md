# AMCE — Phase 2: Graph Analytics, Dependency Mapping & Telemetry Ingestion

**Days 25–34 | BFS Graph Engine, Cycle Detection, Kafka Pipeline, ClickHouse, KS-Test Drift**

---

## Phase Overview

Phase 2 adds two major capability domains to the existing monolith: a dependency graph
engine (PostgreSQL adjacency list + BFS recursive CTEs) and a high-throughput telemetry
pipeline (Kafka → ClickHouse). It also introduces the first analytical layer: statistical drift
detection with the two-sample KS test, latency SLA tracking, and call-volume anomaly
detection.

**Key deliverables:**

- `module_dependencies` adjacency list with self-loop guard, RLS, and BFS recursive CTE
- `GraphEngine.traverse_forward()` with `visited_path` cycle detection and depth cap=50
- `BlastRadiusCalculator` with impact scoring and cycle-aware partial reports
- Kafka topic creation (`amce.telemetry` 12 partitions, `amce.telemetry.dlq`)
- `TelemetryProducer` with deterministic partition routing by `tenant_id:contract_id`
- Kafka consumer → ClickHouse `MergeTree` bulk insert pipeline with at-least-once semantics
- `StatisticalDriftEngine` (KS-2 sample, 30-day baseline, 24h window, APScheduler)
- `LatencySLATracker` (ClickHouse QUANTILE queries) and `CallVolumeMonitor` (Z-score)
- Dependency graph REST API with D3.js format output
- OpenTelemetry spans across the full telemetry pipeline
- 55 integration tests, BFS < 500ms at 100K edges, ClickHouse insert p99 < 2s

---

## Architecture Position

```
Phase 1 monolith
  (contracts, RBAC, auth, bundle endpoint)
         │
         ▼  (Phase 2 extends apps/telemetry-plane)
┌──────────────────────────────────────────────────────────────────┐
│                   apps/telemetry-plane  (extended)                │
│                                                                  │
│  NEW routers:                                                    │
│    /api/v1/graph/*          → GraphRouter                       │
│    /api/v1/contracts/{id}/blast-radius                          │
│    /api/v1/contracts/{id}/analytics                             │
│                                                                  │
│  NEW services:                                                   │
│    GraphEngine              (BFS recursive CTE)                 │
│    BlastRadiusCalculator    (impact scoring)                    │
│    StatisticalDriftEngine   (scipy KS-2 sample)                 │
│    LatencySLATracker        (ClickHouse quantile)               │
│    CallVolumeMonitor        (Z-score anomaly)                   │
│                                                                  │
│  NEW consumers/ (long-running processes):                        │
│    TelemetryConsumer        (Kafka → ClickHouse bulk insert)    │
│                                                                  │
│  NEW infrastructure/:                                            │
│    TelemetryProducer        (confluent_kafka, lz4, acks=all)   │
│    ClickHouseClient         (clickhouse_connect, MergeTree)     │
└─────────────┬──────────────────────────────────┬────────────────┘
              │                                  │
    ┌─────────▼─────────┐            ┌──────────▼──────────┐
    │   PostgreSQL 16    │            │   Apache Kafka       │
    │  module_deps table │            │  amce.telemetry      │
    │  BFS via CTE       │            │  12 partitions       │
    │  drift_reports     │            │  amce.telemetry.dlq  │
    │  sla_events        │            └──────────┬──────────┘
    └───────────────────┘                        │
                                      ┌──────────▼──────────┐
                                      │     ClickHouse       │
                                      │  MergeTree engine    │
                                      │  telemetry_events    │
                                      │  telemetry_minutely  │
                                      │  (materialized view) │
                                      └─────────────────────┘
```

---

## Source Tree

### MVP Layout — Monorepo + Monolith

> Phase 2 extends `apps/telemetry-plane` in-place. New modules are added under new
> subdirectories (`graph/`, `analytics/`, `consumers/`, `infrastructure/`). Nothing from
> Phase 1 is moved or renamed.

```
amce-monorepo/
├── libs/
│   └── amce-core-engine/              ← unchanged from Phase 0
│
├── apps/
│   └── telemetry-plane/
│       ├── alembic/
│       │   └── versions/
│       │       ├── 001_initial_schema.py   (Phase 1)
│       │       ├── 002_contracts.py        (Phase 1)
│       │       ├── 003_telemetry_rbac.py   (Phase 1)
│       │       ├── 004_telemetry_dlq.py    (Phase 1)
│       │       ├── 005_graph.py            ← Day 25: module_dependencies
│       │       ├── 006_drift_reports.py    ← Day 30: drift_reports table
│       │       └── 007_sla_events.py       ← Day 31: sla_events table
│       │
│       └── src/
│           └── amce_telemetry/
│               │   (all Phase 1 files unchanged)
│               │
│               │   ── Graph Domain ──
│               ├── graph/
│               │   ├── __init__.py
│               │   ├── engine.py              ← GraphEngine:
│               │   │                             traverse_forward(source, tenant, max_depth=50)
│               │   │                             BFS recursive CTE with visited_path array
│               │   │                             cycle detection → CycleWarning
│               │   │                             statement_timeout=5000ms guard
│               │   ├── blast_radius.py        ← BlastRadiusCalculator:
│               │   │                             calculate(breached_module_id, tenant_id)
│               │   │                             impact_score = Σ(1/2^depth)
│               │   │                             60s result cache + cycle partial flag
│               │   ├── repository.py          ← DependencyRepository:
│               │   │                             register_dependency(from, to, tenant)
│               │   │                             remove_dependency(from, to, tenant)
│               │   │                             get_neighbors(module_id, tenant)
│               │   │                             get_predecessors(module_id, tenant)
│               │   └── models.py              ← GraphNode, GraphEdge, TraversalResult,
│               │                                 CycleWarning, BlastRadiusReport,
│               │                                 AffectedModule
│               │
│               │   ── Analytics Domain ──
│               ├── analytics/
│               │   ├── __init__.py
│               │   ├── drift_engine.py        ← StatisticalDriftEngine:
│               │   │                             compute_drift(baseline, current, field)
│               │   │                             MIN_SAMPLES=500 guard
│               │   │                             get_baseline() ← ClickHouse 30-day
│               │   │                             get_current_window() ← ClickHouse 24h
│               │   │                             run_drift_analysis() → DriftReport
│               │   │                             APScheduler every 6h, max_instances=1
│               │   ├── sla_tracker.py         ← LatencySLATracker:
│               │   │                             compute_latency_sla() → LatencySLAResult
│               │   │                             ClickHouse quantile(0.5/0.95/0.99)
│               │   │                             SLABreach → sla_events table
│               │   ├── volume_monitor.py      ← CallVolumeMonitor:
│               │   │                             14-day rolling 1h buckets
│               │   │                             Z-score anomaly: |z| > 3.0
│               │   │                             std=0 guard → z_score=None
│               │   └── models.py              ← DriftReport, FieldDriftResult,
│               │                                 LatencySLAResult, SLABreach,
│               │                                 VolumeAnomalyEvent
│               │
│               │   ── Kafka Infrastructure ──
│               ├── infrastructure/
│               │   ├── __init__.py
│               │   ├── kafka_producer.py      ← TelemetryProducer:
│               │   │                             partition_key = tenant_id:contract_id
│               │   │                             acks='all', linger.ms=5, lz4
│               │   │                             delivery callback (log, never raise)
│               │   ├── kafka_admin.py         ← topic creation: amce.telemetry (12p)
│               │   │                             amce.telemetry.dlq (1p)
│               │   │                             idempotent only_if_not_exists
│               │   └── clickhouse_client.py   ← ClickHouseClient:
│               │                                 bulk insert (clickhouse_connect)
│               │                                 region-aware routing (US / EU)
│               │                                 retry wrapper (3×)
│               │
│               │   ── Kafka Consumer (long-running process) ──
│               ├── consumers/
│               │   ├── __init__.py
│               │   └── telemetry_consumer.py  ← TelemetryConsumer:
│               │                                 group.id='amce-telemetry-processors'
│               │                                 enable.auto.commit=False
│               │                                 batch up to 200 msgs / 2s elapsed
│               │                                 clickhouse_insert(batch)
│               │                                 manual commit after insert
│               │                                 DLQ routing after 3 failures
│               │
│               │   ── NEW Routers ──
│               ├── routers/
│               │   ├── ...                    (Phase 1 routers unchanged)
│               │   ├── graph.py               ← POST /api/v1/graph/dependencies
│               │   │                             DELETE /api/v1/graph/dependencies
│               │   │                             GET  /api/v1/graph (D3.js adjacency list)
│               │   │                             GET  /api/v1/graph/traversal?source={id}
│               │   │                             GET  /api/v1/graph/cycles
│               │   └── analytics.py           ← GET /api/v1/contracts/{id}/blast-radius
│               │                                 GET /api/v1/contracts/{id}/analytics
│               │
│               └── otel.py                    ← OpenTelemetry setup:
│                                                 FastAPI instrumentation
│                                                 Kafka span propagation (W3C TraceContext)
│                                                 OTLP exporter (Jaeger in dev)
│
├── infrastructure/
│   └── kafka/
│       └── setup.py                   ← AdminClient topic creation script
│
└── tests/
    (in apps/telemetry-plane/tests/)
    ├── unit/
    │   ├── test_graph_engine.py        ← Day 26: BFS linear chain, cycle detection
    │   ├── test_blast_radius.py        ← Day 27: impact score formula, cycle partial
    │   ├── test_drift_engine.py        ← Day 30: KS test, insufficient data path
    │   └── test_sla_tracker.py         ← Day 31: quantile breach, Z-score anomaly
    ├── api/
    │   └── test_graph_api.py           ← Day 33: D3.js format, cycle endpoint
    ├── db/
    │   ├── test_migration_005.py       ← self-loop guard, RLS, BFS correctness
    │   └── test_dependency_repository.py
    └── integration/
        ├── test_telemetry_pipeline.py  ← Day 32: 1,000 events E2E (HTTP→Kafka→CH)
        └── phase2_suite.py             ← Day 34: 55-test sign-off suite
```

### Future Microservice Extraction Path

> Phase 2 introduces the clearest microservice boundaries in the entire system. The graph
> domain and the telemetry pipeline are independent enough to extract with minimal coupling.

```
[MVP]  apps/telemetry-plane (monolith)
         ├── graph/           ──────────→ [MSvc] svc-graph-analytics
         │   ├── engine.py                  owns: module_dependencies table
         │   ├── blast_radius.py            exposes: /api/v1/graph/*, /blast-radius
         │   └── repository.py              scales: independently per tenant graph size
         │
         ├── analytics/       ──────────→ [MSvc] svc-analytics-engine
         │   ├── drift_engine.py            owns: drift_reports, sla_events tables
         │   ├── sla_tracker.py             reads: ClickHouse (shared)
         │   └── volume_monitor.py          exposes: /api/v1/contracts/{id}/analytics
         │
         ├── infrastructure/  ──────────→ [MSvc] svc-telemetry-ingestion
         │   ├── kafka_producer.py          + routers/telemetry.py from Phase 1
         │   └── clickhouse_client.py       owns: Kafka consumer lifecycle
         │
         └── consumers/       ──────────→ SAME as svc-telemetry-ingestion
             └── telemetry_consumer.py      deployed as a separate container

# Kafka is a shared infrastructure concern — all services can produce/consume
# ClickHouse is shared read — svc-analytics-engine reads, svc-telemetry-ingestion writes
# PostgreSQL: svc-graph-analytics owns its own schema namespace (module_dependencies)

# Extraction order recommendation:
#   1. svc-telemetry-ingestion first (highest isolation, no shared read path)
#   2. svc-graph-analytics second (self-contained, bounded PostgreSQL schema)
#   3. svc-analytics-engine last (reads ClickHouse shared with ingestion service)
```

---

## Database Schema

### Migration 005 — Dependency Graph (Day 25)

```sql
CREATE TABLE module_dependencies (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,    -- RLS enforced
    from_module_id   UUID NOT NULL REFERENCES contracts(id),
    to_module_id     UUID NOT NULL REFERENCES contracts(id),
    dependency_type  VARCHAR(50) NOT NULL DEFAULT 'output_consumer',
    weight           FLOAT NOT NULL DEFAULT 1.0,
    metadata         JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Structural invariants
    CONSTRAINT no_self_loop   CHECK (from_module_id != to_module_id),
    CONSTRAINT unique_edge    UNIQUE(tenant_id, from_module_id, to_module_id)
);

CREATE INDEX idx_deps_from ON module_dependencies(tenant_id, from_module_id);
CREATE INDEX idx_deps_to   ON module_dependencies(tenant_id, to_module_id);

ALTER TABLE module_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE module_dependencies FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON module_dependencies
    USING (tenant_id = current_setting('app.current_org_id')::uuid);
```

### ClickHouse Schema (Day 29)

```sql
CREATE TABLE amce.telemetry_events (
    event_id         UUID     DEFAULT generateUUIDv4(),
    tenant_id        UUID     NOT NULL,
    contract_id      UUID     NOT NULL,
    contract_version String   NOT NULL,
    status           Enum8('pass'=1,'fail'=2,'timeout'=3,'error'=4) NOT NULL,
    duration_ms      Float32  DEFAULT 0.0,
    drift_score      Float32  DEFAULT 0.0,
    breach_details   String   DEFAULT '{}',
    input_hash       String   DEFAULT '',
    created_at       DateTime64(3) NOT NULL
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, contract_id, created_at)
SETTINGS index_granularity = 8192;

-- Pre-computed per-minute aggregation (zero-cost analytics queries)
CREATE MATERIALIZED VIEW amce.telemetry_minutely
ENGINE = SummingMergeTree()
ORDER BY (tenant_id, contract_id, minute_bucket)
AS SELECT
    tenant_id, contract_id,
    toStartOfMinute(created_at) AS minute_bucket,
    countIf(status = 1) AS pass_count,
    countIf(status = 2) AS fail_count,
    avg(duration_ms)    AS avg_duration_ms
FROM amce.telemetry_events
GROUP BY tenant_id, contract_id, minute_bucket;
```

---

## Day-by-Day Implementation Plan

### Day 25 — module_dependencies Adjacency List Schema, RLS, Self-Loop Guard

**Core objective:** Lay the graph data foundation. The CHECK constraint on self-loops is the
only structural enforcement the database can provide — the application must handle logical
cycles via BFS.

**Files created:**

- `apps/telemetry-plane/alembic/versions/005_graph.py`
- `apps/telemetry-plane/src/amce_telemetry/graph/repository.py`
- `apps/telemetry-plane/src/amce_telemetry/graph/models.py`

**Bulk edge insertion pattern (idempotent):**

```sql
INSERT INTO module_dependencies (tenant_id, from_module_id, to_module_id, ...)
VALUES ($1, $2, $3, ...)
ON CONFLICT (tenant_id, from_module_id, to_module_id) DO NOTHING;
```

**Critical edge cases:**

- Self-loop via alias: two UUIDs for same logical module bypass `CHECK` — documented Phase 3 enhancement
- Cross-tenant edges: validate both `from_module_id` and `to_module_id` belong to caller's tenant **before** INSERT
- Edge direction convention: `from_module_id` = producer (output), `to_module_id` = consumer (input) — document explicitly

**Verification:**

```bash
# Self-loop rejected at DB level
pytest tests/db/test_migration_005.py::test_self_loop_guard -v

# RLS prevents cross-tenant edge reads
pytest tests/db/test_dependency_repository.py::test_rls_isolation -v
```

---

### Day 26 — BFS Recursive CTE Engine, visited_path Cycle Guard, Depth Cap=50

**Core objective:** Implement the graph traversal at the database level. The CTE is the correct
choice for the MVP (sub-100K edges) — avoids a round-trip per hop and leverages PostgreSQL's
query optimiser.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/graph/engine.py`

**BFS CTE structure:**

```sql
WITH RECURSIVE dependency_bfs AS (
    -- Anchor: start node
    SELECT
        from_module_id, to_module_id,
        1                       AS depth,
        ARRAY[from_module_id]   AS visited_path,
        FALSE                   AS is_cycle
    FROM module_dependencies
    WHERE from_module_id = $1 AND tenant_id = $2

    UNION ALL

    -- Recursive hop
    SELECT
        md.from_module_id, md.to_module_id,
        bfs.depth + 1,
        bfs.visited_path || md.to_module_id,
        md.to_module_id = ANY(bfs.visited_path)  -- cycle flag
    FROM module_dependencies md
    JOIN dependency_bfs bfs ON md.from_module_id = bfs.to_module_id
    WHERE bfs.depth < 50
      AND NOT bfs.is_cycle
      AND md.tenant_id = $2
)
SELECT DISTINCT to_module_id, depth, visited_path, is_cycle
FROM dependency_bfs
ORDER BY depth;
```

**`TraversalResult` Pydantic model:**

```
TraversalResult:
  nodes:             list[GraphNode]
  edges:             list[GraphEdge]
  cycles_detected:   list[CycleWarning]
  max_depth_reached: bool
  total_nodes:       int
  traversal_time_ms: float
```

**Critical edge cases:**

- `ARRAY = ANY()` is O(depth) per hop: at depth 50, 2,500 comparisons max — acceptable
- Set `statement_timeout = 5000ms` via `SET LOCAL` before executing the CTE
- Empty graph (no outgoing edges): returns `TraversalResult(nodes=[source], edges=[], cycles=[])`
- `LIMIT 100000` on final SELECT: prevents runaway memory on unbounded traversals

**Verification:**

```bash
# 5-node linear chain → correct depth-ordered nodes
pytest tests/unit/test_graph_engine.py::test_bfs_linear_chain -v

# A→B→C→A cycle → CycleWarning(path=[A,B,C], cycle_node=A)
pytest tests/unit/test_graph_engine.py::test_cycle_detection -v

# 1000-node, 2000-edge graph → completes in < 200ms
pytest tests/unit/test_graph_engine.py::test_medium_graph_performance -v
```

---

### Day 27 — BlastRadiusCalculator, Impact Score Formula, GET /blast-radius

**Core objective:** Translate graph traversal results into actionable blast radius data that
product/engineering teams can use to understand breach impact.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/graph/blast_radius.py`
- `apps/telemetry-plane/src/amce_telemetry/routers/analytics.py` (stub, grows Day 31)

**Impact scoring formula:**

```
impact_score = Σ(1 / 2^depth_i)   for each downstream node i
normalised   = impact_score / Σ(1 / 2^1 + 1/2^2 + ... + 1/2^max_depth)
             = impact_score / (1 - 1/2^max_depth) * (1 - 0.5)
```

| Depth | Weight |
| ----- | ------ |
| 1     | 0.5000 |
| 2     | 0.2500 |
| 3     | 0.1250 |
| 4     | 0.0625 |
| ...   | ...    |

**`BlastRadiusReport` model:**

```
BlastRadiusReport:
  affected_modules:    list[AffectedModule]
  cycles_detected:     list[CycleWarning]
  impact_score:        float  (0.0 – 1.0, 6 decimal places)
  total_affected:      int
  user_facing_features: list[str]
  is_partial:          bool   (True when cycles prevent full traversal)
```

**Critical edge cases:**

- Disconnected node: `impact_score=0.0`, `affected_modules=[]` — valid result, not an error
- `1/2^50 ≈ 8.9e-16`: rounds to 0 in display — clip to 6 decimal places
- `is_user_facing` missing from `contracts.metadata`: treat as `False`, never raise `KeyError`
- 60s cache: invalidate on dependency graph change (`register_dependency`, `remove_dependency`)

---

### Day 28 — Kafka Topic Creation, TelemetryProducer

**Core objective:** Set up the Kafka infrastructure and the producer with production-grade
configuration. The producer is used both by the Phase 1 telemetry endpoint stub (upgraded
to real) and by the Phase 3 benchmark engine.

**Files created:**

- `infrastructure/kafka/setup.py`
- `apps/telemetry-plane/src/amce_telemetry/infrastructure/kafka_producer.py`
- `apps/telemetry-plane/src/amce_telemetry/infrastructure/kafka_admin.py`

**Producer configuration:**

```python
Producer({
    'bootstrap.servers': bootstrap_servers,
    'acks':              'all',          # strongest delivery guarantee
    'linger.ms':         5,              # 5ms batching (set to 0 in tests)
    'batch.size':        65536,          # 64KB batches
    'compression.type':  'lz4',          # fast compression for JSON
    'retries':           3,
    'retry.backoff.ms':  100,
    'metadata.max.age.ms': 60000,        # fast broker failover detection
})
```

**Partition routing:** `partition_key = f"{tenant_id}:{contract_id}".encode("utf-8")`
→ all events for a given contract go to the same partition (in-order consumer processing)

**Topic specification:**

| Topic                | Partitions | Retention | Notes                          |
| -------------------- | ---------- | --------- | ------------------------------ |
| `amce.telemetry`     | 12         | 7 days    | `lz4` compression              |
| `amce.telemetry.dlq` | 1          | 30 days   | No compression (debuggability) |

**Critical edge cases:**

- `AdminClient.create_topics()`: check existence first — idempotent setup script
- DLQ messages: must be JSON-serialisable — convert `datetime` to ISO string before publish
- `linger.ms=5` adds 5ms latency — set to 0 in test configuration

---

### Day 29 — Kafka Consumer, ClickHouse MergeTree Table, Bulk Insert Pipeline, DLQ After 3 Failures

**Core objective:** Build the consumer that bridges Kafka events into ClickHouse. This runs
as a separate long-lived process (not as a FastAPI route) with independent restart policy.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/consumers/telemetry_consumer.py`
- `apps/telemetry-plane/src/amce_telemetry/infrastructure/clickhouse_client.py`

**Consumer loop design:**

```python
# At-least-once semantics: commit only after successful ClickHouse insert
while True:
    msg = consumer.poll(timeout=1.0)
    batch.append(msg)
    # Drain up to 200 or 2-second window
    if len(batch) >= 200 or elapsed > 2.0:
        clickhouse_client.bulk_insert("telemetry_events", batch)
        consumer.commit()   # manual commit after insert
        batch = []
```

**Failure handling:**

```
ClickHouse insert fails (attempt 1) → retry
ClickHouse insert fails (attempt 2) → retry
ClickHouse insert fails (attempt 3) → produce all N events to amce.telemetry.dlq
                                       commit offset (event acknowledged, routed to DLQ)
```

**Critical edge cases:**

- Rebalance during bulk insert: `enable.auto.commit=False` + manual commit ensures at-least-once
- Consumer lag alert: `> 10,000 messages` → log CRITICAL; heartbeat: 3s / session timeout: 10s
- `insert_distributed_sync=1` in tests: forces synchronous ClickHouse writes for deterministic assertions

**Process isolation:**

```bash
# Development: separate terminal
uv run python -m amce_telemetry.consumers.telemetry_consumer

# Production: separate Kubernetes Deployment
# apps/telemetry-plane/k8s/telemetry-consumer-deployment.yaml
```

---

### Day 30 — StatisticalDriftEngine: scipy.stats.ks_2samp, APScheduler

**Core objective:** Continuously monitor the statistical distribution of each contract field's
output values. Alert when a model's output distribution shifts significantly from its baseline.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/analytics/drift_engine.py`
- `apps/telemetry-plane/alembic/versions/006_drift_reports.py`

**KS test parameters:**

| Parameter       | Value    | Rationale                                            |
| --------------- | -------- | ---------------------------------------------------- |
| Minimum samples | 500      | Below this → false positives from small-sample noise |
| `ks_threshold`  | 0.10     | Maximum ECDF difference to trigger drift             |
| `alpha`         | 0.05     | p-value threshold for statistical significance       |
| Baseline window | 30 days  | Stable reference distribution                        |
| Current window  | 24 hours | Recent observation window                            |

**Severity mapping:**

| KS statistic | Severity |
| ------------ | -------- |
| > 0.20       | HIGH     |
| > 0.10       | MEDIUM   |
| > 0.00       | LOW      |

**Critical edge cases:**

- Non-numeric fields: skip with WARNING — KS test requires continuous numeric distributions
- ClickHouse timeout (30-day query on large tenant): use `telemetry_minutely` materialized view + 15s timeout
- APScheduler `max_instances=1`: prevents overlapping 6-hour runs
- New contract (< 500 samples): return `status='INSUFFICIENT_DATA'`, never run KS test

---

### Day 31 — LatencySLATracker, CallVolumeMonitor (Z-Score, 14-Day Rolling)

**Core objective:** Provide SLA breach alerting and traffic anomaly detection directly from the
ClickHouse telemetry data, surfaced via the analytics API endpoint.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/analytics/sla_tracker.py`
- `apps/telemetry-plane/src/amce_telemetry/analytics/volume_monitor.py`
- `apps/telemetry-plane/alembic/versions/007_sla_events.py`

**ClickHouse SLA query:**

```sql
SELECT
    quantile(0.50)(duration_ms) AS p50,
    quantile(0.95)(duration_ms) AS p95,
    quantile(0.99)(duration_ms) AS p99
FROM amce.telemetry_events
WHERE tenant_id = {tenant_id:UUID}
  AND contract_id = {contract_id:UUID}
  AND created_at > now() - INTERVAL {hours} HOUR
```

**Z-score computation (with zero-std guard):**

```python
def compute_zscore(self, current: float, history: list[float]) -> float | None:
    mean = statistics.mean(history)
    std  = statistics.stdev(history) if len(history) > 1 else 0.0
    if std == 0.0:
        return None   # STABLE — not ANOMALY
    return (current - mean) / std
```

**Critical edge cases:**

- `quantile()` vs `quantileExact()`: switch to exact for samples < 1,000 rows (1-2% error in t-Digest)
- SLA breach suppression: < 100 events in window → no breach emitted (cold start noise)
- UTC anchors: all `INTERVAL` queries use UTC — never apply local timezone offsets
- Z-score undefined (std=0): return `z_score=None, status='STABLE'` — never divide by zero

---

### Day 32 — Full Telemetry Pipeline Integration Test, OpenTelemetry Spans, Backpressure Test

**Core objective:** Verify the entire path from HTTP ingest to ClickHouse row, with distributed
tracing across all hops and proof that the API never blocks under high event volume.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/otel.py`
- `apps/telemetry-plane/tests/integration/test_telemetry_pipeline.py`

**OpenTelemetry span hierarchy:**

```
HTTP POST /api/v1/telemetry      [FastAPI auto-instrumentation]
  └── kafka.produce              [custom span: telemetry_producer.py]
        └── kafka.consume        [custom span: telemetry_consumer.py]
              └── clickhouse.insert [custom span: clickhouse_client.py]
```

**W3C TraceContext propagation across Kafka:**

```python
# Producer: inject trace context into message headers
from opentelemetry.propagate import inject
headers = {}
inject(headers)   # adds 'traceparent' and 'tracestate'
producer.produce(topic, key=..., value=..., headers=list(headers.items()))

# Consumer: extract trace context from message headers
from opentelemetry.propagate import extract
context = extract(dict(msg.headers() or []))
with tracer.start_as_current_span("kafka.consume", context=context):
    ...
```

**Backpressure verification:**

```
10,000 events, 10 concurrent threads
  → API max latency must be < 10ms regardless of queue depth
  → Zero 5xx responses
  → asyncio.Queue(maxsize=50_000) as in-process buffer
```

**Critical edge cases:**

- ClickHouse async insert buffer: poll with 500ms retry up to 15s in tests (not fixed sleep)
- Kafka consumer group session timeout during slow tests: `heartbeat.interval.ms=3000`
- `insert_settings={'async_insert': 0}` in tests for synchronous ClickHouse writes

---

### Day 33 — Dependency Graph REST API, Register/Query/GET graph, Cycles, D3.js Format

**Core objective:** Expose the graph engine as a REST API. The D3.js output format enables
the frontend to directly render the dependency graph without transformation.

**Files created:**

- `apps/telemetry-plane/src/amce_telemetry/routers/graph.py`

**D3.js response format:**

```json
{
  "nodes": [
    {
      "id": "uuid-string",
      "name": "summariser-v1",
      "status": "active",
      "impact_score": 0.875
    }
  ],
  "links": [
    {
      "source": "uuid-string",
      "target": "uuid-string",
      "type": "output_consumer"
    }
  ]
}
```

**Cycles endpoint algorithm:** Tarjan's SCC (Strongly Connected Components) — O(V+E) —
rather than BFS-from-every-node O(V\*(V+E))

**Critical edge cases:**

- UUID serialisation: `str(uuid)` in all JSON output — not `UUID` objects
- Deleted contract referenced in edges: return placeholder node `{"type": "DELETED"}` — not `KeyError`
- Large graph response: `summary=true` query parameter returns aggregate statistics only (> 10K nodes)
- Pagination: cursor-based on nodes list, `default_page_size=200`, `max=1000`

---

### Day 34 — Phase 2 Sign-Off: 55 Tests, BFS<500ms at 100K Edges, ClickHouse Insert p99<2s

**Core objective:** Final verification under production-scale data volumes.

**Synthetic 100K-edge graph generation:**

```python
# Balanced binary tree of depth 17 → ~131K nodes, ~130K edges
# Stresses BFS without creating hub nodes that would explode traversal
def generate_binary_tree(depth: int, tenant_id: UUID) -> list[dict]:
    nodes = [uuid4() for _ in range(2**depth - 1)]
    edges = []
    for i in range(len(nodes) // 2):
        edges.append({"from": nodes[i], "to": nodes[2*i+1], "tenant_id": tenant_id})
        edges.append({"from": nodes[i], "to": nodes[2*i+2], "tenant_id": tenant_id})
    return edges
```

**Sign-off checklist:**

| Criterion                  | Target                                | Tool                        |
| -------------------------- | ------------------------------------- | --------------------------- |
| Integration test count     | 55/55 passing                         | pytest                      |
| BFS on 100K-edge graph     | < 500ms                               | pytest-benchmark            |
| ClickHouse bulk insert p99 | < 2s for 10K events                   | pytest-benchmark            |
| Full drift pipeline        | MEDIUM/HIGH severity detected         | StatisticalDriftEngine test |
| E2E telemetry pipeline     | 1,000 events in ClickHouse within 15s | integration test            |
| OpenTelemetry trace        | 4 spans visible in Jaeger             | manual + test               |

```bash
pytest tests/integration/phase2_suite.py -v --tb=short

# BFS performance
pytest tests/unit/test_graph_engine.py::test_100k_edge_performance \
    --benchmark-autosave -v

git tag -a v0.1.0-phase2-complete \
    -m "Phase 2: Graph Analytics & Telemetry. 55/55 tests. BFS<500ms."
```

---

## Dependencies Added in Phase 2

```toml
# Additions to apps/telemetry-plane/pyproject.toml
"confluent-kafka>=2.4",         # Kafka producer + consumer
"clickhouse-connect>=0.7",      # ClickHouse Python client
"apscheduler>=3.10",            # drift analysis scheduler
"scipy>=1.13",                  # KS-2 sample test
"numpy>=2.0",                   # array operations
"opentelemetry-sdk>=1.24",
"opentelemetry-instrumentation-fastapi>=0.45b0",
"opentelemetry-exporter-otlp>=1.24",
```

---

## Nx Commands for This Phase

```bash
# Start telemetry consumer (separate terminal)
nx run telemetry-plane:consume

# Set up Kafka topics
nx run telemetry-plane:kafka-setup

# Run ClickHouse DDL
nx run telemetry-plane:clickhouse-setup

# Full integration test suite (requires all Docker services)
nx test-integration telemetry-plane

# Performance benchmark
nx test-benchmark telemetry-plane
```

---

## Migration Path: Monolith → Microservices

```
Phase 2 introduces the natural split points:

svc-graph-analytics:
  Boundary:    module_dependencies table + all graph/* modules
  Trigger:     tenant graph sizes exceed single PostgreSQL capacity
  Extraction:  add graph schema namespace; expose /api/v1/graph/* on dedicated service
  Scaling:     horizontal by tenant — each tenant's graph can route to a dedicated shard

svc-telemetry-ingestion:
  Boundary:    routers/telemetry.py + consumers/ + infrastructure/kafka_producer.py
  Trigger:     telemetry ingest volume requires independent scaling from contract management
  Extraction:  deploy consumers/ as separate Kubernetes Deployment TODAY
               (consumers already run as a separate process — this is just a deployment change)
  Scaling:     Kafka consumer group scaling = add Deployment replicas (max=12 for 12 partitions)

svc-analytics-engine:
  Boundary:    analytics/ modules + drift_reports/sla_events tables
  Trigger:     drift analysis jobs compete with API latency on shared process
  Extraction:  APScheduler jobs move to dedicated worker service
  Scaling:     CPU-bound (scipy) — horizontal workers per region

Key insight: consumers/ is already process-isolated — the microservice extraction
is purely a deployment topology change, not a code change.
```
