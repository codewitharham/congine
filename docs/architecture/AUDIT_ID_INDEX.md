# Audit-ID index

**Canonical index of every audit ID used in `libs/congine-sdk/src/`.** This codebase
uses no `TODO`/`FIXME` comments; it annotates deliberate remediations with IDs
instead, and this file is what makes that trail readable.

**Maintenance rule (audit Q12).** This index is *maintained*, not archival. Any
change that introduces or closes an audit ID must update this file in the same
commit, and the code it touches must carry the ID that motivated it. Definitions
live in:

| Series | Defined in |
|---|---|
| `F-*` | `docs/audits/PHASE0_AUDIT_AND_HEALTH.md` |
| `Q*` | `docs/architecture/OPEN_QUESTIONS.md` |
| `P0-*` | `docs/audits/PHASE0_COMPLETION_ROADMAP.md` |
| `FIX-*`, `H*`, `M*`, `D-*`, `C*`, `L*` | original audit docs — **not present in this repository**, see §4 |

Last reconciled against source: 2026-08-09.

---

## 1. Active series

### Q* — decisions from the current architecture review

Resolved in `docs/architecture/OPEN_QUESTIONS.md`; each row records what shipped.

| ID | Meaning | Annotated at |
|---|---|---|
| **Q1** | `region` wired to a regional default `base_url` — it was a validated, documented, unread field | `config.py` (`_REGION_BASE_URLS`, `Region.default_base_url`, `base_url_from_env`) |
| **Q2** | Union `type` declarations (`["string","null"]`) enforced instead of crashing the rule engine; `"null"` added to `_JSON_TYPE_MAP` | `domain/validator.py` (`_type_matches`, `_type_label`, `_JSON_TYPE_MAP`), `domain/schema_vocabulary.py` (`RECOGNISED_TYPE_NAMES`, `_type_is_enforceable`) |
| **Q3** | `null_forbidden` documented as a Congine extension, not JSON Schema; portable spelling recommended | `domain/validator.py` (`RuleEngine.NULL_GUARD`) |
| **Q4** | The unenforced-keyword scan is a **required step for every schema writer**, enforced by a convention test | `domain/schema_vocabulary.py` (module docstring), `domain/__init__.py` |
| **Q5** | Deferred teardown armed at construction for **every** container, not only evicted ones | `adapters/dependency_injection.py` (`__init__`, `_arm_deferred_teardown`, `for_tenant`) |
| **Q6** | Python floor unified at 3.11 across `requires-python`, classifiers, ruff `target-version`, CI matrix | `pyproject.toml`, `.github/workflows/ci.yml` |
| **Q7** | README config table completed (47/47) and made drift-proof by a test | `README.md`, `tests/unit/test_readme_config_table.py` |
| **Q8** | `ports/lifecycle.py` (`IStoppable`, `IObservable`); the previously-undeclared lifecycle/observability surface now declared on the ports that need it | `ports/lifecycle.py`, `ports/schema_storage.py`, `ports/event_bus.py`, `ports/validation_runner.py` |
| **Q9** | **Decision, no code change.** Telemetry stays fire-and-forget by default; durability arrives as a *second* `IEventBus` implementation selected by config, never by making the default bus blocking. Q8 is its prerequisite | recorded here and in `ports/event_bus.py` |
| **Q10** | `get_default()` reads one environment variable on the cached path instead of parsing and validating all 47 | `adapters/dependency_injection.py` (`get_default`, `_deployment_mode_is_multi_tenant`), `config.py` (`deployment_mode_from_env`) |
| **Q11** | `max_contract_file_bytes` split out of `max_schema_bytes` — one knob was capping two unrelated limits | `security_limits.py`, `config.py`, `adapters/dependency_injection.py` |
| **Q12** | This index, plus the maintenance rule in `.claude/CLAUDE.md` | this file |

### P0-* — post-audit priority items

| ID | Meaning | Annotated at |
|---|---|---|
| **P0-1** | Safe tenant-container eviction: remove the registry entry and arm a `weakref.finalize`; never `close()` a possibly-live container, never tear down under `_tenant_lock` | `adapters/dependency_injection.py` `:78`, `:124`, `:156`, `:183`, `:199`, `:204` |
| **P0-2** | Load-time WARNING naming schema keywords the rule engine silently ignores, de-duplicated per `(contract_id, schema fingerprint)` | `domain/schema_vocabulary.py`, `usecases/sync_contracts_usecase.py` `:40`, `:73`, `:275` |

### F-* — findings from `PHASE0_AUDIT_AND_HEALTH.md`

Only those referenced from source are listed; the audit document is authoritative
for the rest.

| ID | Meaning | Status |
|---|---|---|
| **F-2** | Silent non-enforcement of `minLength`/`maxLength`/`format` (false safety) | addressed by P0-2 (detection) — enforcement still requires `CONGINE_SEMANTIC_VALIDATION=true` |
| **F-15** | `IEventBus` omits the lifecycle/observability surface the container needs | **closed by Q8** |
| **F-17** | `region` is a dead configurable | **closed by Q1** |
| **F-3** | `requires-python` contradiction breaks the advertised 3.10 floor and CI | **closed by Q6** |
| **F-9** | Byte-named size budget measured in characters | reclassified: the measure is *conservative* (over-counts), not permissive — see `README.md` note under the config table |

---

## 2. Legacy series (still annotated in source)

These predate the F/Q series. Their definitions come from audit documents that are
**not in this repository** (§4), but each meaning below is derived from the
annotated code itself and is reliable.

### FIX-* — numbered remediations

| ID | Meaning | Annotated at |
|---|---|---|
| **FIX-01** | Loopback detection by parsed **hostname**, not substring (rejects `localhost.evil.com`) | `config.py:30`, `:288` |
| **FIX-02** | `google-re2` promoted to a required core dependency; `[redos]` is a no-op alias | `domain/validator.py:37` |
| **FIX-03** | Hard cap on semantic breaches drained from `iter_errors`, with a truncation marker | `jsonschema_validator.py:85`, `security_limits.py:21` |
| **FIX-04** | Redact instance values out of breach messages before logs/telemetry | `pii_sanitize.py:4` |
| **FIX-05** | `get_default()` disabled in `multi_tenant` mode | `adapters/dependency_injection.py:87`, `config.py:138` |
| **FIX-06** | Input bounding: payload, schema, contract-file count, file size, stream buffer, HTTP response | `config.py:141`, `file_contract_repository.py:45`, `security_limits.py:14` |
| **FIX-08** | Log redaction: unconditional sensitive-key blocklist + non-local auto-allowlist | `config.py:298`, `logger.py:31` |
| **FIX-11** | HALF_OPEN admits exactly one probe caller (`_probe_in_flight`) | `circuit_breaker.py:83` |
| **FIX-14** | `start_background_services` gates the executor atexit hook, cache sweeper and telemetry drain thread | `config.py:148`, `adapters/dependency_injection.py` |

Two unnumbered `(FIX)` markers remain in `adapters/dependency_injection.py`
(`NoOpEventBus` leaves no trailing daemon; standalone mode allocates no sync
worker). Give them IDs the next time that code is touched.

### H* — high severity

| ID | Meaning | Annotated at |
|---|---|---|
| **H1** | Bounded, load-shedding validation execution (`BoundedSemaphore`, permit held until the future completes) | `bounded_executor.py:5`, `:114`, `guard.py:92`, `ports/validation_runner.py:35` |
| **H2** | Async parity — the async twin uses the *same* bounded pool, never a raw `run_in_executor` | `bounded_executor.py:114`, `guard.py:91`, `ports/validation_runner.py:35` |
| **H3** | ReDoS defence: length-capped patterns and values, linear-time engine | `domain/validator.py:248`, `security_limits.py:10` |
| **H4** | Configuration completeness and HTTPS/credential policy for non-local control planes | `config.py:258` |

> **Naming collision, do not conflate.** `H-1` in
> `adapters/dependency_injection.py:124` is the *eviction* finding (the P0-1
> subject), not the executor `H1` above.

### M*, D-*, C*, L* — medium / design / cross-cutting / low

| ID | Meaning | Annotated at |
|---|---|---|
| **M1** | Drift wiring is an opt-in library capability, not an automatic pipeline | `adapters/dependency_injection.py` (`record_drift_sample`, `evaluate_drift`) — **backfilled by Q12** |
| **M2** | Bounded exit flush (single attempt) + long-lived HTTP client reuse | `queue_event_bus.py:174`, `:203` |
| **M4** | `_min_freq` reconciled off the hot path rather than scanned on every TTL expiry | `lfu_cache.py:181` |
| **M5** | Guard return modes (`envelope`/`output`/`raise`) plus `extractor` | `guard.py:7` |
| **D-3** / **D-11** | `ValidationTimer` deprecated and deliberately not exported — wiring it defeats load-shedding and async symmetry | `infrastructure/__init__.py:22`, `timer.py:10` |
| **D-4** | `IValidationRunner` port introduced so L3 depends on an L1 abstraction | `ports/validation_runner.py:9` |
| **D-7** | Single-flight boot via a per-scope `portalocker` lock, distinct from the snapshot-write lock | `http_contract_repository.py:75`, `usecases/sync_contracts_usecase.py:27`, `:124` |
| **D-10** | `dropped_total` counter — a visible telemetry-loss signal surfaced in `health()` | `queue_event_bus.py:80` |
| **C1** | Lazy, double-checked process-wide singleton | `adapters/dependency_injection.py` (`get_default`) — **backfilled by Q12** |
| **C2** | Snapshot security and isolation: scoped path, per-user dir, atomic write, cross-process lock, load-time refusal | `http_contract_repository.py:8`, `:166` |
| **L2** | `health()` aggregation across components | `adapters/dependency_injection.py` (`health`) — **backfilled by Q12** |
| **L4** | Tier-2 exception aliases are compatibility shims, not distinct raised types | `exceptions.py:57` |
| **L5** | Logger level threshold so per-drain DEBUG output is silent in production | `logger.py:5` |
| **L6** | `bootstrap()` refuses to run inside a running event loop | `adapters/dependency_injection.py` (`bootstrap`) — **backfilled by Q12** |
| **L7** | `TelemetryEvent` frozen so an enqueued event cannot be mutated under the drain worker | `domain/models.py:78` |

> `config.py:95` mentions "L4" as a **layer**, not an audit ID.

---

## 3. Backfill performed under Q12

Four IDs were referenced in the test suite's section comments but carried no
annotation in `src/`. Their meanings were recoverable from the tests that assert
them, and they are now annotated:

| ID | Recovered from | Now annotated at |
|---|---|---|
| **C1** | `tests/adversarial/test_remediations.py:47` `# --- C1: process-wide singleton ---` | `get_default()` docstring |
| **M1** | `:79` `# --- M1 + L2: drift wiring & health ---` | `record_drift_sample()` / `evaluate_drift()` docstrings |
| **L2** | `:79` (same section) | `health()` docstring |
| **L6** | `:120` `# --- L6: bootstrap loop-safety ---` | `bootstrap()` docstring |

## 4. Unrecoverable IDs — deliberately not invented

The following are referenced by the 2026-06-14 audit set as part of contiguous
ranges, but appear **nowhere** in `src/` or `tests/`, and the audit documents that
defined them (`phase0-congine-newAudit.md`,
`phase0-congine-postSessionAudit.md`, cited by `.claude/CLAUDE.md`) are not in
this repository:

> **FIX-07, FIX-09, FIX-10, FIX-12, FIX-13, M3, D-5, D-6, D-8, D-9**

They are recorded here as *unrecoverable* rather than guessed. Assigning them
invented meanings would be worse than leaving the gap, because it would make a
fabricated trail indistinguishable from a real one. If the original audit
documents resurface, add them here.

`docs/context/01_SYSTEM_STATE.md:88` asserts the full `FIX-01..FIX-14` range is
"present and consistent with the implemented behavior". That is not accurate:
**9 of 14 are annotated.**

## 5. Coverage summary

| Series | Annotated in `src/` | Notes |
|---|---|---|
| `Q*` | 12 | all closed in this change set except Q9 (a decision) |
| `P0-*` | 2 | both landed |
| `F-*` | 5 referenced | full set in `PHASE0_AUDIT_AND_HEALTH.md` |
| `FIX-*` | 9 of 14 | 5 unrecoverable (§4) |
| `H*` | 4 of 4 | complete |
| `M*` | 4 (M1, M2, M4, M5) | M3 unrecoverable |
| `D-*` | 5 (D-3, D-4, D-7, D-10, D-11) | D-5, D-6, D-8, D-9 unrecoverable |
| `C*` | 2 (C1, C2) | complete |
| `L*` | 5 (L2, L4, L5, L6, L7) | complete for the known range |
