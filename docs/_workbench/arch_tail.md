## 17. Open questions for the founder

Each of these is a decision the code cannot answer and that materially affects the next phase.
Numbered for citation.

**Q1 — Is `region` meant to do something?** It validates, it is documented with GDPR connotations
(`config.py:40-42`), and nothing reads it (§12.4, D1). Should it derive a default `base_url`, travel
as a header, or be deleted? A user setting `CONGINE_REGION=eu` for data-residency reasons today gets
nothing and is told nothing.

**Q2 — Should a union `type` be supported, or rejected loudly?** `{"type": ["string","null"]}` is
idiomatic JSON Schema and currently degrades every validation silently (§13.6, D18). Two coherent
answers: make `_type_matches` accept a list (correct JSON Schema semantics, ~3 lines), or reject
such a schema at load with an error rather than a warning. The current third state — accept, then
crash at validation time — is the only indefensible one.

**Q3 — Is `null_forbidden` a permanent part of the contract language?** It is a Congine extension
with no JSON Schema equivalent, enforced by the rule engine and invisible to the semantic validator
(§13.3). If contracts are meant to be portable JSON Schema, this is a divergence to decide about
before contracts ship to users. If it stays, `{"type": ["string","null"]}` (Q2) needs an answer,
because that is what users will otherwise write.

**Q4 — Should the P0-2 scan move behind `ISchemaStorage.put`?** Today it fires only on the
cache-prime path (D17), so every future loader the roadmap adds — MCP server, CLI, direct injection
— reopens the silent-keyword trap. Moving it costs a little purity; leaving it means each new entry
point must remember.

**Q5 — Should an evicted-but-referenced tenant container keep running forever?** P0-1 correctly
stopped eviction from *breaking* live containers; the trade is that they now *leak* (D3). Arming the
finalizer in `__init__` rather than at eviction would make every container self-cleaning. Is that
the intended semantics, or should eviction be refused when a container is still referenced?

**Q6 — Is the Python floor 3.10 or 3.11?** `pyproject.toml:6` says `>=3.11`; `:18` classifies 3.10;
`:69` pins ruff to `py310`; `.claude/CLAUDE.md` says 3.10. The comment at `:66-68` asserts 3.10–3.13
is "the declared `requires-python` floor", contradicting `:6` in the same file. This blocks nothing
today but it will produce a confusing install failure for someone.

**Q7 — Should the README config table be generated?** It documents 27 of 46 fields (D2), and the
project's own conventions designate it the canonical user-facing config doc. A test that asserts the
table covers `dataclasses.fields(CongineConfig)` would make this class of drift impossible.

**Q8 — Should the ports declare their lifecycle surface?** Three ports require methods they do not
declare (§5.9, D14). This becomes concrete the moment `SqliteEventBus` is written: a faithful
implementation of `IEventBus` as declared will `AttributeError` in `health()` and `close()`.

**Q9 — Is telemetry meant to be durable?** Today it is explicitly not (G11, §14.11): queue-full,
retry-exhaustion, breaker-OPEN and process death all drop events silently apart from a counter.
Phase C in the roadmap treats the event log as "the data spine" that capability profiles and history
queries are computed from. Those two positions are incompatible, and the reconciliation (a durable
store behind the same port, §15.2) should be a deliberate decision rather than an emergent one.

**Q10 — Should `@congine_guard` without an explicit `container=` remain supported?** It re-reads and
re-validates ~46 environment variables on **every guarded call** (D8). It is the documented
convenience path and the one every example uses. Fixing the cost is ~5 lines; the alternative is to
document it as unsuitable for production, which the README already hints at but does not state.

**Q11 — Is `max_schema_bytes` deliberately doing two jobs?** It bounds the cached-schema check *and*
caps per-contract-file reads (D21). Tuning one silently changes the other.

**Q12 — What is the intended relationship between the audit-ID trail and the roadmap?** Nine of
fourteen `FIX-*` IDs, five of nine `D-*`, three of four `M*` and three of four `L*` appear in the
source (Appendix B). The prior audit asserted the full `FIX-01..FIX-14` range was present and
consistent. Either the missing IDs were closed elsewhere and the annotation was not added, or they
were never annotated. That trail is unusually valuable raw material and it is worth deciding whether
it is maintained or archived.

---

## Appendix A — Complete file-to-file linkage map

All 37 files. **Depends on (runtime)** = imports at runtime, Congine modules only.
**TC** = `TYPE_CHECKING`-only, no runtime edge. **Depended on by** = Congine modules importing it
(aggregate `__init__.py` re-exports omitted for readability, except where they are the only
consumer).

| # | File | L | Depends on (runtime) | TC | Depended on by |
|---|---|---|---|---|---|
| 1 | `__init__.py` | root | `ports`, `domain`, `usecases`, `infrastructure`, `adapters`, `config`, `exceptions` | — | *(package surface; nothing imports it internally)* |
| 2 | `config.py` | 0 | `exceptions`, `security_limits` | — | `validate_contract_usecase`, `http_contract_repository`, `queue_event_bus`, `dependency_injection`, `langchain_handler`, `__init__` |
| 3 | `exceptions.py` | 0 | — | — | `config`, `validate_contract_usecase`, `sync_contracts_usecase`, `http_contract_repository`, `jsonschema_validator`, `dependency_injection`, `guard`, `langchain_handler`, `__init__` |
| 4 | `security_limits.py` | 0 | — | — | `config`, `domain/validator`, `jsonschema_validator`, `langchain_handler` |
| 5 | `pii_sanitize.py` | 0 | — | — | `validate_contract_usecase`, `jsonschema_validator` |
| 6 | `ports/__init__.py` | 1 | the 7 port modules | — | `congine_core/__init__` |
| 7 | `ports/schema_storage.py` | 1 | — | — | `validate_contract_usecase`, `sync_contracts_usecase`, `ports/__init__` |
| 8 | `ports/contract_repository.py` | 1 | — | — | `sync_contracts_usecase`, `dependency_injection`, `ports/__init__` |
| 9 | `ports/event_bus.py` | 1 | — | `domain.models` | `validate_contract_usecase`, `dependency_injection`, `ports/__init__` |
| 10 | `ports/logger.py` | 1 | — | — | both use cases, `http_contract_repository`, `file_contract_repository`, `queue_event_bus`, `background_sync`, `ports/__init__` |
| 11 | `ports/semantic_validator.py` | 1 | — | `domain.models` | `domain/validator` (TC), `ports/__init__` |
| 12 | `ports/validation_runner.py` | 1 | — | — | `validate_contract_usecase`, `ports/__init__` |
| 13 | `ports/circuit_breaker.py` | 1 | — | — | `sync_contracts_usecase` (TC), `queue_event_bus` (TC), `ports/__init__` |
| 14 | `domain/__init__.py` | 2 | `domain.models`, `domain.validator` | — | `congine_core/__init__` |
| 15 | `domain/models.py` | 2 | — | — | `domain/validator`, `validate_contract_usecase`, `jsonschema_validator`, `ks_drift`, `dependency_injection`; TC from `ports/event_bus`, `ports/semantic_validator`, `noop_event_bus`, `queue_event_bus`, `langchain_handler` |
| 16 | `domain/validator.py` | 2 | `domain.models`, `security_limits` | `ports.semantic_validator` | `validate_contract_usecase`, `dependency_injection`, `domain/__init__` |
| 17 | `domain/schema_vocabulary.py` | 2 | — | — | `sync_contracts_usecase` **(new since baseline)** |
| 18 | `usecases/__init__.py` | 3 | both use cases | — | `congine_core/__init__` |
| 19 | `usecases/validate_contract_usecase.py` | 3 | `config`, `domain.models`, `domain.validator`, `exceptions`, `pii_sanitize`, `ports.event_bus`, `ports.logger`, `ports.schema_storage`, `ports.validation_runner` | — | `dependency_injection`, `usecases/__init__` |
| 20 | `usecases/sync_contracts_usecase.py` | 3 | `domain.schema_vocabulary`, `exceptions`, `ports.contract_repository`, `ports.logger`, `ports.schema_storage` | `ports.circuit_breaker` | `dependency_injection`, `background_sync` (TC), `usecases/__init__` |
| 21 | `infrastructure/__init__.py` | 4 | 11 concretes (**not** `timer`) | — | `congine_core/__init__` |
| 22 | `infrastructure/bounded_executor.py` | 4 | — | — | `dependency_injection`, `infrastructure/__init__` |
| 23 | `infrastructure/lfu_cache.py` | 4 | — | — | `dependency_injection`, `infrastructure/__init__` |
| 24 | `infrastructure/circuit_breaker.py` | 4 | — | — | `dependency_injection`, `infrastructure/__init__` |
| 25 | `infrastructure/logger.py` | 4 | — | — | `dependency_injection`, `infrastructure/__init__` |
| 26 | `infrastructure/http_contract_repository.py` | 4 | `config`, `exceptions`, `ports.logger` | — | `dependency_injection`, `infrastructure/__init__` |
| 27 | `infrastructure/file_contract_repository.py` | 4 | `ports.logger` | — | `dependency_injection`, `infrastructure/__init__` |
| 28 | `infrastructure/queue_event_bus.py` | 4 | `config`, `ports.logger` | `domain.models`, `ports.circuit_breaker` | `dependency_injection`, `infrastructure/__init__` |
| 29 | `infrastructure/noop_event_bus.py` | 4 | — | `domain.models` | `dependency_injection`, `infrastructure/__init__` |
| 30 | `infrastructure/jsonschema_validator.py` | 4 | `domain.models`, `exceptions`, `pii_sanitize`, `security_limits` | — | `dependency_injection`, `infrastructure/__init__` |
| 31 | `infrastructure/ks_drift.py` | 4 | `domain.models` | — | `dependency_injection`, `infrastructure/__init__` |
| 32 | `infrastructure/background_sync.py` | 4 | `ports.logger` | `usecases.sync_contracts_usecase` | `dependency_injection`, `infrastructure/__init__` |
| 33 | `infrastructure/timer.py` | 4 | — | — | **nothing** — deprecated, unwired; only `tests/unit/test_timer.py` |
| 34 | `adapters/__init__.py` | 5 | `dependency_injection`, `guard`; `langchain_handler` lazily via `__getattr__` | — | `congine_core/__init__` |
| 35 | `adapters/dependency_injection.py` | 5 | `config`, `exceptions`, `domain.models`, `domain.validator`, **all 10 wired concretes**, **both use cases**, `ports.contract_repository`, `ports.event_bus` | `domain.models` | `guard`, `langchain_handler` (lazy), `adapters/__init__` |
| 36 | `adapters/guard.py` | 5 | `dependency_injection`, `exceptions` | — | `adapters/__init__`, host code |
| 37 | `adapters/langchain_handler.py` | 5 | `dependency_injection`, `config`, `exceptions`, `security_limits` — **all function-local** | `dependency_injection`, `domain.models` | `adapters/__init__` (lazy), host code |

**How to trace a path by hand.** "What does a guarded call touch?" Start at `guard.py` (36) → it
imports `dependency_injection` (35) to resolve the container, then calls
`container.validate_contract_usecase` → that is `validate_contract_usecase.py` (19) → which names
`ports/schema_storage` (7), `ports/validation_runner` (12), `domain/validator` (16) and
`ports/event_bus` (9). To learn which concrete each port resolves to, read §6 — the bindings are made
in exactly one place, `dependency_injection.py:202-335`.

**Files no runtime edge reaches:** `infrastructure/timer.py` (deprecated) and
`congine_core/__init__.py` (the package surface, imported only by consumers).

---

## Appendix B — Audit-ID index

The codebase uses no `TODO`/`FIXME` (verified: zero matches in `src/`). It annotates deliberate
remediations with audit IDs instead. Every occurrence in `src/` is listed below, with the meaning
derived from the annotated code.

### B.1 P0 — the post-audit priority items

| ID | Locations | Meaning |
|---|---|---|
| **P0-1** | `dependency_injection.py:78`, `:124`, `:156`, `:183`, `:199`, `:204` | **Safe tenant-container eviction.** Eviction removes the registry entry and arms a `weakref.finalize` instead of calling `close()` on a possibly-live container; no teardown runs under `_tenant_lock`; `close()` is idempotent; `reset_default()` closes outside both locks; `_evicted_total` is exposed. Also cited as **H-1** at `:124`. **Landed, committed** |
| **P0-2** | `schema_vocabulary.py:6`, `sync_contracts_usecase.py:40`, `:73`, `:275` | **Unenforced-keyword diagnostic.** A load-time WARNING naming schema keywords the rule engine silently ignores, de-duplicated per `(contract_id, schema fingerprint)`, bounded at 4 096 entries, skipped when semantic validation is on. **Landed, uncommitted** |
| **F-2** | `schema_vocabulary.py:6` | Alternate identifier for the same finding as P0-2 |

### B.2 FIX-* — the numbered remediation series

| ID | Locations | Meaning |
|---|---|---|
| **FIX-01** | `config.py:30`, `:288` | Loopback detection by **parsed hostname**, not substring — rejects `localhost.evil.com` and `notlocalhost` |
| **FIX-02** | `domain/validator.py:37` | `google-re2` promoted to a **required core dependency**; the `[redos]` extra is a no-op alias |
| **FIX-03** | `jsonschema_validator.py:85`, `security_limits.py:21` | Hard cap on semantic breaches drained from `iter_errors` (100), with a `SEMANTIC_TRUNCATED` marker |
| **FIX-04** | `pii_sanitize.py:4` | Redact instance values out of breach messages before they reach logs or telemetry |
| **FIX-05** | `dependency_injection.py:87`, `config.py:138` | `get_default()` disabled in `multi_tenant` mode; explicit `container=` or `for_tenant()` required |
| **FIX-06** | `config.py:141`, `file_contract_repository.py:45`, `security_limits.py:14` | Input bounding: payload, schema, contract-file count, file size, stream buffer, HTTP response |
| **FIX-08** | `config.py:298`, `logger.py:31` | Log redaction: an unconditional sensitive-key blocklist plus a non-local auto-allowlist |
| **FIX-11** | `circuit_breaker.py:83` | HALF_OPEN admits exactly **one** probe caller (`_probe_in_flight`); concurrent callers get `False` |
| **FIX-14** | `config.py:148`, `dependency_injection.py:342` | `start_background_services` gates the executor atexit hook, the cache sweeper, and the telemetry drain thread |
| **(FIX)** *(unnumbered)* | `dependency_injection.py:264`, `:324` | Two unnumbered markers: `NoOpEventBus` leaves no trailing daemon at shutdown; standalone mode allocates no sync worker |

**Not present in `src/`: FIX-07, FIX-09, FIX-10, FIX-12, FIX-13.** `docs/context/01_SYSTEM_STATE.md:88`
asserts the full `FIX-01..FIX-14` range is "present and consistent with the implemented behavior";
**9 of 14 are annotated.** The other five were either closed without annotation or never annotated.
See Q12.

### B.3 H* — high-severity audit findings

| ID | Locations | Meaning |
|---|---|---|
| **H1** | `bounded_executor.py:5`, `:114`, `guard.py:92`, `ports/validation_runner.py:35` | **Bounded, load-shedding validation execution.** A vanilla `ThreadPoolExecutor` has an unbounded queue; timed-out callables cannot be killed, so a burst fills every worker with zombies while submissions pile up. Replaced by a `BoundedSemaphore` with permit-until-completion |
| **H2** | `bounded_executor.py:114`, `guard.py:91`, `ports/validation_runner.py:35` | **Async parity.** `run_with_timeout_async` offloads onto the *same* bounded pool via `wrap_future` + `wait_for` — no raw `run_in_executor` bypass, no event-loop blocking |
| **H3** | `domain/validator.py:248`, `security_limits.py:10` | **ReDoS defence.** Schema-supplied patterns are untrusted: cap pattern (1 000) and value (50 000) length fail-closed, cache compiled patterns, use a linear-time engine |
| **H4** | `config.py:258` | **Configuration completeness and security policy.** Non-local base URLs require credentials and HTTPS unless explicitly opted out |

All four are present. `H-1` at `dependency_injection.py:124` is a *different* finding (it labels the
P0-1 lock-holding issue), not the executor H1 — worth noting when grepping.

### B.4 M* — medium-severity audit findings

| ID | Locations | Meaning |
|---|---|---|
| **M2** | `queue_event_bus.py:174`, `:203` | **Bounded exit flush + connection reuse.** The atexit flush uses a single attempt per batch so a dead plane cannot add retry×backoff seconds to shutdown; one long-lived `httpx.Client` is reused across batches and retries |
| **M4** | `lfu_cache.py:181` | **`_min_freq` reconciliation off the hot path.** TTL expiry can empty the min bucket without a scan; `_evict_lfu` reconciles lazily instead of scanning on every expiry |
| **M5** | `guard.py:7` | **Guard return modes.** `envelope` / `output` / `raise`, plus an `extractor` for non-dict outputs, so a wrapped function need not be rewritten to unwrap an envelope |

**Not present in `src/`: M3.**

### B.5 D-* — design/debt audit findings

| ID | Locations | Meaning |
|---|---|---|
| **D-3** | `infrastructure/__init__.py:22`, `timer.py:10` | `ValidationTimer` is **not exported** — wiring it directly produces an unbounded, non-load-shedding timer |
| **D-4** | `ports/validation_runner.py:9` | **`IValidationRunner` port introduced** so L3 is typed against an L1 abstraction rather than naming an L4 concrete |
| **D-7** | `http_contract_repository.py:75`, `sync_contracts_usecase.py:27`, `:124` | **Single-flight boot.** A per-scope `portalocker` lock, distinct from the snapshot-write lock, so one worker per host issues the initial fetch |
| **D-10** | `queue_event_bus.py:80` | **`dropped_total` counter** — a visible loss signal for queue-full and retry-exhausted drops, surfaced in `health()` |
| **D-11** | `infrastructure/__init__.py:22`, `timer.py:10` | Paired with D-3: the deprecation rationale for `ValidationTimer` |

**Not present in `src/`: D-5, D-6, D-8, D-9.**

### B.6 L* — low-severity audit findings

| ID | Locations | Meaning |
|---|---|---|
| **L4** | `exceptions.py:57` | **Tier-2 aliases are compatibility shims, not distinct types.** A validation timeout degrades rather than raising `ValidationTimeoutException`; `TenantIsolationViolationException` is a forward-compat placeholder |
| **L5** | `logger.py:5` | **Level threshold** so per-drain `DEBUG` telemetry is silent in production |
| **L7** | `domain/models.py:78` | **`TelemetryEvent` is frozen** so a caller cannot mutate an enqueued event and race the drain worker. (Shallow — `breach_details` is still a mutable list; see debt D5) |

**Not present in `src/`: L6.**
`config.py:95`'s mention of "L4" is a **layer** reference, not an audit ID.

### B.7 C* — cross-cutting

| ID | Locations | Meaning |
|---|---|---|
| **C2** | `http_contract_repository.py:8`, `:166` | **Snapshot security and isolation.** Per-`(base_url, project_id, tenant_id)` SHA-256 path under a per-user app directory (never a world-shared temp root); atomic `tempfile` + `os.replace` under an advisory cross-process lock; symlink and non-owner refusal on load; envelope validation |

### B.8 Coverage summary

| Series | Annotated in `src/` | Referenced by the prior audit | Missing |
|---|---|---|---|
| `P0-*` | P0-1, P0-2 | *(post-dates the audit)* | — |
| `FIX-*` | 01, 02, 03, 04, 05, 06, 08, 11, 14 (**9**) | 01–14 (**14**) | 07, 09, 10, 12, 13 |
| `H*` | H1, H2, H3, H4 (**4**) | H1–H4 (**4**) | — |
| `M*` | M2, M4, M5 (**3**) | M2–M5 (**4**) | M3 |
| `D-*` | D-3, D-4, D-7, D-10, D-11 (**5**) | D-3–D-11 (**9**) | D-5, D-6, D-8, D-9 |
| `L*` | L4, L5, L7 (**3**) | L4–L7 (**4**) | L6 |
| `C*` | C2 (**1**) | C2 (**1**) | — |
| **Total** | **27 distinct IDs across 56 source annotations** | 40 claimed | 13 unannotated |
