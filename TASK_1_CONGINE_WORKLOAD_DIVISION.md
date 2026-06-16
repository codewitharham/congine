# CONGINE — TWO-DEVELOPER WORKLOAD DIVISION
## Phase-by-Phase, Day-by-Day Build Plan: Ahmed & Partner
### Starting Date: June 15, 2026 | Total Plan Horizon: 4 Weeks (20 Working Days)

> **How to read this document.** Each day is a self-contained unit. Every task for every developer has a defined
> START condition (what must exist before you touch it), a set of subtasks in order, and an END condition (what
> "done" concretely means — no ambiguity). The end of each day includes a synchronization checkpoint and the exact
> line to append to `CONGINE_PROGRESS.md` via the Document 3 daily tracker prompt. The workload between Dev A and
> Dev B is designed to be **exactly equal in cognitive weight** — not necessarily identical in LOC, because some
> tasks are more architecturally complex than others. Where one dev has a harder problem, their partner has more
> breadth. Track this with the daily tracker every single evening.

---

## SECTION 0 — CONTEXT, PRINCIPLES & OWNERSHIP PHILOSOPHY

### 0.1 Who Does What — Permanent Track Assignments

Rather than deciding each task ad-hoc, this plan permanently assigns each developer to a **track** that aligns
with the system's own layer boundaries. This minimises merge conflicts, keeps each developer in their zone of
deep context, and mirrors how the hexagonal architecture separates concerns.

| Developer | Track | Primary Layer Ownership | Secondary |
|-----------|-------|------------------------|-----------|
| **Dev A (Ahmed)** | **Core/Domain Track** | L2 Domain, L3 Use Cases, MCP Server, Phase 2 Intelligence | L1 Ports (when adding new ports) |
| **Dev B (Partner)** | **Infrastructure/Adapter Track** | L4 Infrastructure, L5 Adapters, CLI, CI/CD, SQLite, Tests | L0 Config (when adding knobs) |

**Why this split works:** the hexagonal architecture's fundamental property is that L2 and L3 never import L4 or
L5. So Dev A and Dev B can write code on the same day with near-zero merge conflict risk, because their layers
literally do not depend on each other at runtime. Their hand-off point is always an L1 `typing.Protocol` — the
port — which both can refer to without either blocking the other.

### 0.2 How to Hand Off Between Tracks

Every inter-developer dependency follows this protocol:
1. **Dev A defines the port** (the `typing.Protocol` in `ports/`) when a new capability is needed across a layer
   boundary. This is the contract between the two tracks.
2. **Dev B implements the concrete** in `infrastructure/` or `adapters/`, satisfying the protocol structurally
   (no subclassing required, per the project's duck-typing convention).
3. **Dev A writes the use case** against the port (not the concrete). It will never know Dev B's concrete exists.
4. **Dev B wires the concrete** into `dependency_injection.py` — the sole composition root.
5. **Both write tests independently.** Dev A writes unit tests using fake port implementations (conftest.py
   already has the pattern). Dev B writes integration tests using the real concrete.

This protocol means neither developer is ever blocked waiting for the other — they can always develop against
a stub/fake and integrate at the end of the day.

### 0.3 Daily Tracker Integration

At the **end of every working day**, one developer (rotate daily — today's turn is noted at the bottom of each
day) runs the Document 3 daily tracker prompt in Claude Code:
- Paste the entire `03_CLAUDE_CODE_PROMPT_daily_tracker.md` content into Claude Code
- Claude Code will read `CONGINE_PROGRESS.md`, inspect `git log`, `git diff`, and `git status`
- It will append a dated entry to the DAILY LOG

This means: **every task listed below must be committed by end of day** so the tracker can see it. Use the
suggested git commit messages at the bottom of each day section.

### 0.4 Equal Workload Accounting

Over the 20-day plan, here is the overall workload balance:
- Dev A owns: B9 (hardest Phase 0 item), contract version pinning, schema keyword warning, README config table,
  MCP server (all tools + transport), ValidateArchUseCase, ArchGraph domain model, Phase 2 MCP integration.
- Dev B owns: All remaining Phase 0 fixes (7 items, mostly small), SqliteEventBus, ValidationEvent, CLI,
  diff_parser, GitHub Actions, correction_hint infra, all infrastructure tests.

Each developer carries approximately **50% of the total LOC and 50% of the total cognitive difficulty** across
the plan. The weights are balanced so that Dev A's fewer-but-harder tasks equal Dev B's more-numerous-but-smaller
tasks in total effort per day.

---

## SECTION 1 — PHASE 0: HARDEN THE CORE
### Week 1 | June 15–19, 2026 | Goal: Ship v0.1.1 with all known defects resolved

**Phase 0 "Done" criteria (from CONGINE_PROGRESS.md):** multi-tenant eviction is refcount/idle-safe **with a direct
test**; `requires-python` reconciled; WARNING fires for unenforced keywords with semantic off; example runs offline
without raising; byte-accurate size bounds; docstring/dead-code cleaned; `test_container.py` covers
`bootstrap()` loop-guard, `health()`, `evaluate_drift()`, `reset_default()`. **Git tag: `v0.1.1`.**

---

### DAY 1 — Monday, June 15 — Multi-Tenant Eviction + Python Floor + Docs Fixes

**Theme:** The two hardest correctness items: Dev A fixes the most critical bug (B9), Dev B eliminates the most
embarrassing doc/config inconsistency (A1) and lays groundwork for B14.

---

#### DEV A — Task Focus: Multi-Tenant Container Eviction Fix (B9 — HIGH PRIORITY)

**Files:** `adapters/dependency_injection.py:72-118` | `tests/unit/test_container.py` (new)
**Complexity:** HIGH | **Effort:** Full day (6–7 hrs)

---

**TASK A1.1: Deep-read the existing eviction code before touching anything**

> *Start condition: nothing. This is a read-first task.*

- Open `adapters/dependency_injection.py`, read lines 60–130 completely.
- Understand the current `_tenant_registry: dict[str, ServiceContainer]` structure, the `_tenant_order` list,
  and how `for_tenant()` (line 72) currently works: it moves the entry to the end of `_tenant_order` on lookup
  (LRU-on-lookup), and when `len > _tenant_cap`, calls `close()` on the first entry in `_tenant_order`.
- **Identify the bug precisely:** `close()` is called on the `_tenant_registry[oldest_tenant_id]` container while
  a request that already resolved that container from `for_tenant()` may still be mid-validation. The container
  being closed tears the `LFUCache`, `QueueEventBus` daemon, and `BoundedValidationExecutor` out from under it.
- Write a one-paragraph diagnosis comment in your notes (or a scratch file). Do not write code yet.

---

**TASK A1.2: Design the fix — reference counting approach**

> *Start condition: A1.1 complete and diagnosis written.*

The fix is to add a reference counter to the per-tenant container so that `close()` is deferred until the
reference count drops to zero. Here is the design:

```python
# In ServiceContainer, add:
_ref_count: int = 0          # protected by the same lock as the tenant registry

# In for_tenant():
with cls._tenant_lock:
    if tenant_id in cls._tenant_registry:
        container = cls._tenant_registry[tenant_id]
        container._ref_count += 1   # <-- increment before returning
        # move to end (LRU recency)
        cls._tenant_order.remove(tenant_id)
        cls._tenant_order.append(tenant_id)
        return container
    # ... construct new container (set _ref_count = 1)

# Add a new context manager / release helper:
def release(self):
    with self._tenant_lock:   # or a per-container lock
        self._ref_count -= 1
        if self._ref_count == 0 and self._pending_close:
            self._do_close()    # actual close deferred

# In eviction:
if len(cls._tenant_registry) > cls._tenant_cap:
    oldest = cls._tenant_order[0]
    victim = cls._tenant_registry[oldest]
    if victim._ref_count == 0:
        victim.close()        # safe to close right now
    else:
        victim._pending_close = True   # close when ref drops to 0
    cls._tenant_registry.pop(oldest)
    cls._tenant_order.pop(0)
```

- Sketch this on paper / in a scratch file.
- Check that the existing `conftest.py` fakes will still work after this change (they should — fakes don't
  go through `for_tenant()`).
- Decide whether the ref count needs its own lock or whether the existing `_tenant_lock` is sufficient.
  (It is sufficient if every path that increments or decrements the ref count holds `_tenant_lock` first.)

---

**TASK A1.3: Implement the fix in dependency_injection.py**

> *Start condition: A1.2 design approved by you mentally; scratch notes ready.*

- Edit `adapters/dependency_injection.py`.
- Add `_ref_count: int = 0` and `_pending_close: bool = False` to `ServiceContainer.__init__`.
- Add a `release()` method to `ServiceContainer` (call it from `for_tenant()` context manager or document
  that callers must call it — see below).
- Convert `for_tenant()` to be a context manager that auto-releases:

  ```python
  @classmethod
  @contextlib.contextmanager
  def for_tenant(cls, tenant_id: str):
      with cls._tenant_lock:
          container = cls._get_or_create_tenant(tenant_id)
          container._ref_count += 1
      try:
          yield container
      finally:
          container.release()
  ```

- Update all existing call sites of `for_tenant()` to the context manager form
  (search for `for_tenant(` in the codebase — there may be call sites in tests).
- Implement the deferred-close logic in `release()` and in the eviction branch.
- Add the carry-forward comment: `# FIX-B9: deferred close; ref-counted per-tenant lifecycle`.

---

**TASK A1.4: Write test_container.py**

> *Start condition: A1.3 implemented and the existing test suite still passes.*

Create `tests/unit/test_container.py` (or add to it if it exists). Write tests covering:

1. **Test: eviction defers close while ref is live**
   - Acquire a tenant container via `for_tenant()` context manager.
   - While inside the context, trigger eviction (mock `_tenant_cap` to 1 and add a second tenant).
   - Assert the first container's daemons are still alive inside the context.
   - Exit the context. Assert `close()` was called.

2. **Test: bootstrap() refuses to run inside a running event loop**
   - Already exists or partially exists; ensure it's here.
   - Use `asyncio.get_event_loop().run_until_complete(...)` to create a running loop, then assert
     `bootstrap()` raises inside it.

3. **Test: health() returns expected keys**
   - Construct a container, call `health()`, assert the returned dict has
     `validation_executor`, `telemetry_bus`, `schema_cache`, `circuit_breaker` keys.

4. **Test: evaluate_drift() returns a DriftResult**
   - Add reference samples, call `evaluate_drift()`, assert the result is a `DriftResult`.

5. **Test: reset_default() clears the singleton**
   - Get the default container, reset, get again — should be a new object (different `id()`).

6. **Test: get_default() raises in multi_tenant mode**
   - Set `DeploymentMode.MULTI_TENANT` in config, assert `get_default()` raises.

**END criteria for Dev A Day 1:**
- `dependency_injection.py` has the refcount/idle-safe eviction.
- `tests/unit/test_container.py` has all 6 tests passing.
- `git diff` shows only the expected files changed.
- `pytest tests/unit/test_container.py tests/unit/test_config.py -v` → all green.

---

#### DEV B — Task Focus: Python Floor Fix (A1) + Architecture Doc Fix (A2/A3) + Changelog (A5) + Schema Keyword Vocabulary Groundwork (B14 part 1)

**Files:** `pyproject.toml`, `ARCHITECTURE.md`, `CHANGELOG.md`, `domain/validator.py` (read-only today)
**Complexity:** LOW–MEDIUM | **Effort:** Full day (4–5 hrs coding + 2 hrs reading for B14 groundwork)

---

**TASK B1.1: Fix pyproject.toml Python floor (A1)**

> *Start condition: nothing. This is a single-line change.*

- Open `pyproject.toml`.
- Change `requires-python = ">=3.11"` to `requires-python = ">=3.10"`.
- Verify: `pyproject.toml` classifiers already list `Programming Language :: Python :: 3.10`.
  Ruff's `target-version = "py310"` already targets 3.10. These are now consistent.
- Run `uv pip install -e ".[dev]"` to confirm the install resolves under 3.10 metadata.
- Commit this alone as a micro-commit: `fix(config): reconcile requires-python to 3.10 floor (A1)`.

---

**TASK B1.2: Fix ARCHITECTURE.md (A2 + A3)**

> *Start condition: B1.1 committed.*

Open `ARCHITECTURE.md` and make two fixes:
1. **A2 — Rename `repositories/` to `ports/`:** Find every reference to "`repositories/`" in the layer diagram
   (line 11) and in any protocol-placement rule (line 21). Replace with "`ports/`". The rename was recorded in
   `CHANGELOG.md` as audit D-11.
2. **A3 — Fix "5-layer" to "6-tier":** Find the header that says "strict 5-layer Clean/Hexagonal design" and
   change to "strict 6-tier Clean/Hexagonal design (L0–L5)". Confirm all six layers are listed.
- Cross-check against `README.md` and `.claude/CLAUDE.md` (which correctly say "6-tier" and "ports/") to
  confirm your edits match those references.
- Commit: `docs(architecture): fix ports/ rename reference and 5→6 tier count (A2, A3)`.

---

**TASK B1.3: Fix CHANGELOG.md (A5)**

> *Start condition: B1.2 committed.*

- Open `CHANGELOG.md`.
- Locate the gap between `FIX-11` and `FIX-13` in the Phase 0 Lockdown list.
- Add a note: `<!-- FIX-12: Audit ID retired/consolidated — no corresponding code change. See 03_SPEC_RECONCILIATION.md A5. -->`
- This preserves the audit-ID trail so comments in source code that reference FIX-12 don't appear orphaned.
- Commit: `docs(changelog): note FIX-12 gap for audit-ID traceability (A5)`.

---

**TASK B1.4: Read domain/validator.py completely — B14 groundwork (READ-ONLY today)**

> *Start condition: B1.3 committed. This is preparation for B14, which Dev A will implement on Day 3.*

- Open `domain/validator.py`.
- Read `LocalValidator._extract_params` (line ~333) completely. Write down in a scratch note:
  - Every JSON Schema keyword currently handled: `required`, `properties` (type), `enum`, `min`/`max`/
    `minimum`/`maximum`, `pattern`, `null_forbidden`.
  - Every JSON Schema keyword **not** handled: `minLength`, `maxLength`, `format`, `$ref`,
    nested `object` properties, `additionalProperties`, `allOf`, `anyOf`, `oneOf`, `not`.
- Also read the `RuleEngine.RULES` list (if it exists as a named collection) and understand
  how each rule maps to schema keywords.
- Open the example contracts at `examples/LangChain/contracts/`: read `return_processing.json`,
  `support_reply.json`, `weather_policy.json`. Note which keywords appear in them that are **not**
  in the handled set (the `minLength: 10` in `return_processing.json:summary` is the known example).
- Produce a written "vocabulary gap list" (a Markdown scratch file or a comment in your notes):
  ```
  HANDLED: required, type (per property), enum, minimum/maximum, pattern, null_forbidden
  NOT HANDLED (silently ignored when semantic=off):
    - minLength, maxLength (appears in return_processing.json:summary)
    - format (date, email, uri patterns)
    - $ref (cross-schema references)
    - additionalProperties (object schema strictness)
    - allOf / anyOf / oneOf / not (composition)
    - nested object validation (only top-level properties checked)
  ```
- **This list becomes the input for Dev A's B14 implementation on Day 3.**
- Share the list with Dev A tonight (commit to a `scratch/b14_keyword_gap.md` file, or just message).
- Do NOT modify `domain/validator.py` today — this is Dev A's layer.

---

**TASK B1.5: Start README config table completion (A4) — first half**

> *Start condition: B1.4 scratch note complete.*

The README config table currently omits many `CONGINE_*` env vars. Start filling it:
- Open `config.py` and read `CongineConfig.from_env()` completely.
- Open `README.md` and find the config table.
- For every env var in `from_env()` that is NOT in the README table, draft a row:
  ```
  | CONGINE_ENV_VAR_NAME | Default | Description |
  ```
  Focus on the first 10+ missing entries today:
  `CONGINE_LOCAL_CONTRACTS_DIR`, `CONGINE_CONTRACT_SOURCE`, `CONGINE_CONTRACTS_DIR`,
  `CONGINE_TELEMETRY_ENABLED`, the five `CONGINE_TELEMETRY_*` knobs,
  `CONGINE_CONTROL_PLANE_HTTP_TIMEOUT`, `CONGINE_SNAPSHOT_LOCK_TIMEOUT`.
- Do not commit yet — Dev A will finish the second half on Day 3 and you'll merge it together.
- Save progress to `scratch/a4_config_table_draft.md`.

**END criteria for Dev B Day 1:**
- `pyproject.toml` has `requires-python = ">=3.10"`.
- `ARCHITECTURE.md` says "6-tier" and references "ports/".
- `CHANGELOG.md` has the FIX-12 note.
- `scratch/b14_keyword_gap.md` exists with the complete vocabulary gap list.
- `scratch/a4_config_table_draft.md` has at least 10 rows.
- All commits are pushed.

---

#### END-OF-DAY SYNC — Day 1

**Synchronization checkpoint (after both devs finish their tasks):**
1. Both run `pytest -x -q` — confirm the full suite still passes (Dev B's changes are pure docs/config,
   should not affect tests; Dev A's eviction fix should make `test_container.py` all-green).
2. Dev A walks Dev B through the refcount fix in `dependency_injection.py` in 10 minutes.
3. Dev B shares the `scratch/b14_keyword_gap.md` with Dev A — Dev A needs this for Day 3.

**Suggested commit messages:**
- Dev A: `fix(di): refcount-safe per-tenant eviction; deferred close (B9)` | `test(container): add direct lifecycle tests for bootstrap, health, drift, reset, multi-tenant`
- Dev B: (already committed per task)

**Daily Tracker:** Dev B runs the Document 3 tracker prompt tonight.
**Active Phase:** Phase 0 | **State:** IN PROGRESS

---

### DAY 2 — Tuesday, June 16 — Contract Version Pinning + Batch Small Fixes

**Theme:** Dev A extends the cache architecture; Dev B clears all remaining small correctness items in one focused session.

---

#### DEV A — Task Focus: Contract Version Pinning (Codex Item #2)

**Files:** `infrastructure/lfu_cache.py`, `usecases/validate_contract_usecase.py`, `usecases/sync_contracts_usecase.py`, `ports/schema_storage.py`
**Complexity:** MEDIUM | **Effort:** 5–6 hrs

---

**TASK A2.1: Read the current cache key path**

> *Start condition: Day 1 complete. B9 fix merged.*

- Read `infrastructure/lfu_cache.py` completely. Note that `get(contract_id)` and `put(contract_id, schema)`
  use `contract_id` as the sole key (a plain `str`).
- Read `usecases/validate_contract_usecase.py:_resolve_schema()`. It passes `contract_id` only.
- Read `usecases/sync_contracts_usecase.py:_apply()`. It calls `schema_storage.put(contract_id, schema)`.
- Also read `ports/schema_storage.py` — the `ISchemaStorage` Protocol: `get(key: str) → dict | None` and
  `put(key: str, schema: dict)`.
- **Identify the change scope:** The key type changes from `str` (just `contract_id`) to a **tuple**
  `(contract_id, version)`. You need to decide: do you change the port signature, or do you encode the tuple
  as a string key? Recommendation: **encode as a string** `f"{contract_id}@{version}"` to avoid changing the
  port signature (which would require updating all fakes and mocks). Record this decision.

---

**TASK A2.2: Update validate_contract_usecase.py**

- In `execute(payload, contract_id, contract_version)`, update `_resolve_schema` to call
  `schema_storage.get(f"{contract_id}@{contract_version}")`.
- Similarly, update the schema size check to use the composite key.
- The `contract_version` parameter already exists on the use case (it's threaded into telemetry). 
  You are just extending it to the cache lookup.
- Update the docstring: note that the cache key is `"{contract_id}@{version}"`.

---

**TASK A2.3: Update sync_contracts_usecase.py and lfu_cache.py**

- In `sync_contracts_usecase.py:_apply()`, change `schema_storage.put(contract_id, schema)` to
  `schema_storage.put(f"{contract_id}@{contract['version']}", schema)`.
  - Verify: the fetched contracts dict has a `version` field (check `http_contract_repository.py`'s
    returned schema format). If the field name differs, use the correct one.
- In `lfu_cache.py`, the `get/put/exists/clear` methods need no signature change (they still take `str key`).
  The composite string `"contract_id@version"` is opaque to the cache — which is exactly right.
- Add a brief comment in `lfu_cache.py`: `# Key format: '{contract_id}@{version}'. Single source of truth in validate_contract_usecase.py`.

---

**TASK A2.4: Update tests for version pinning**

- In `tests/unit/test_usecase.py`, find the existing test for `_resolve_schema`. Update the fake
  `ISchemaStorage` put/get calls to use the new `"{contract_id}@{version}"` key format.
- Add a new test: `test_different_versions_get_different_schemas()`:
  - Put `("contract_a@v1", schema_v1)` and `("contract_a@v2", schema_v2)` into the cache.
  - Execute validation with `contract_version="v1"` → should use `schema_v1`.
  - Execute validation with `contract_version="v2"` → should use `schema_v2`.
  - Assert the correct schema was used (you can detect this by the breach output).
- Add a test in `tests/unit/test_cache.py` verifying the cache can hold two different version keys
  for the same contract_id simultaneously.

**END criteria for Dev A Day 2:**
- Cache key is `"{contract_id}@{version}"` end-to-end from guard to cache.
- All tests pass.
- `pytest tests/unit/test_usecase.py tests/unit/test_cache.py -v` → green.

---

#### DEV B — Task Focus: Batch of Small Correctness Fixes (B10, B11, B6, A6, timer cleanup)

**Files:** `usecases/validate_contract_usecase.py:125,143`, `domain/validator.py:436`, `pii_sanitize.py`, `domain/models.py`, `infrastructure/timer.py`
**Complexity:** LOW per item | **Effort:** Full day (all 5 items)

---

**TASK B2.1: Fix size bounds char → byte (B10)**

> *Start condition: nothing beyond Day 1 completion.*

- Open `usecases/validate_contract_usecase.py`, find `_check_payload_size` (line ~125) and `_check_schema_size` (line ~143).
- Current code: `len(json.dumps(payload, default=str))` — this counts **characters**, not **bytes**.
- Fix: `len(json.dumps(payload, default=str).encode("utf-8"))`.
- Do this for **both** `_check_payload_size` and `_check_schema_size`.
- Update the docstrings for both methods to say "UTF-8 byte count".
- Run `pytest tests/unit/test_input_bounds.py` to confirm existing tests still pass. Add one assertion
  in that test file that a payload with multibyte characters is correctly rejected when it exceeds the byte
  budget (construct a payload with enough ≥U+0080 characters to be under the character limit but over the
  byte limit).
- Commit: `fix(usecase): size guards now count UTF-8 bytes, not characters (B10)`.

---

**TASK B2.2: Fix CompositeValidator non-dict short-circuit (B11)**

- Open `domain/validator.py`, find `CompositeValidator.validate()` (line ~436).
- Current code runs `self.rule_validator.validate(payload, schema)` and then **unconditionally** calls
  `self.semantic_validator.validate(payload, schema)` regardless of whether payload is a dict.
- Fix: add a guard before the semantic call:
  ```python
  if not isinstance(payload, dict):
      # rule_validator already produced a non-dict failure; skip semantic validator
      return rule_result
  semantic_breaches = self.semantic_validator.validate(payload, schema)
  return ValidationResult(...)  # merge rule_result + semantic_breaches
  ```
- Run `pytest tests/unit/test_composite_validator.py -v`. Add a test:
  `test_composite_skips_semantic_on_non_dict()` — pass a list as payload to `CompositeValidator.validate()`,
  assert the result is a fail (from the rule validator), and assert the semantic validator was **not** called
  (use a spy/mock to verify the `validate` call count is 0 on the semantic side).
- Commit: `fix(domain): CompositeValidator short-circuits semantic on non-dict payload (B11)`.

---

**TASK B2.3: Fix pii_sanitize.py to use re2 (B6 partial)**

- Open `pii_sanitize.py`. The current import is `import re` (stdlib).
- The function `sanitize_breach_message()` uses `re.sub()` to strip quoted substrings and digit runs.
- Replace `import re` with `import re2`.
- The `re2` module has a compatible API (`re2.sub()` works exactly like `re.sub()`).
- **Important:** verify that the patterns used in `pii_sanitize.py` are valid `re2` patterns. They should be
  simple (quoted-string and digit patterns) and will work fine with `re2`.
- Run `pytest tests/unit/test_pii_sanitization.py -v` to confirm behaviour is unchanged.
- Commit: `fix(security): pii_sanitize now uses re2 for linear-time guarantee (B6)`.

---

**TASK B2.4: Fix stale TelemetryEvent docstring (A6)**

- Open `domain/models.py`.
- Find the module-level docstring (lines 5–6) that says "the outbound `TelemetryEvent` is mutable to allow
  post-init defaulting."
- The class is `@dataclass(frozen=True)` and uses `object.__setattr__` precisely because it is frozen.
  The docstring is backwards.
- Fix the docstring to say: "The `TelemetryEvent` is a **frozen** dataclass; `object.__setattr__` is used in
  `__post_init__` exclusively to set defaults on frozen fields, a standard pattern (not mutation)."
- Commit: `docs(models): fix stale TelemetryEvent mutable/frozen docstring (A6)`.

---

**TASK B2.5: Quarantine ValidationTimer dead code**

- Open `infrastructure/timer.py`. The class `ValidationTimer` is deprecated, not wired in
  `dependency_injection.py`, and emits a warning on construction.
- Do NOT delete it yet — there may be existing test coverage at `tests/unit/test_timer.py` that documents
  the deprecated behaviour. Check if that test file exists and what it asserts.
- Add a module-level comment at the top of `timer.py`:
  ```python
  # DEPRECATED: ValidationTimer is not wired and will be removed in v0.2.0.
  # The replacement is BoundedValidationExecutor (infrastructure/bounded_executor.py).
  # This file is retained for backward compatibility during Phase 0 and for the
  # test_timer.py test that documents the deprecation warning behaviour.
  # DO NOT use ValidationTimer in new code.
  ```
- Exclude `ValidationTimer` from `infrastructure/__init__.py`'s `__all__` if it isn't already excluded
  (check that `infrastructure/__init__` deliberately excludes it per the inventory comment).
- Commit: `refactor(infra): mark ValidationTimer deprecated; exclude from public __init__ (Phase 0 cleanup)`.

**END criteria for Dev B Day 2:**
- Five commits: B10, B11, B6, A6, timer.
- `pytest tests/ -x -q` → all green (no regressions).
- Every commit message is clean and traceable to the audit ID.

---

#### END-OF-DAY SYNC — Day 2

1. Both run `pytest -x -q`. Should be 100% green.
2. Dev A explains the version-pinning key scheme to Dev B (since B will encounter `"{contract_id}@{version}"` in their future SQLite work).
3. Dev B shows Dev A the vocabulary gap list from yesterday — Dev A now plans the B14 implementation for tomorrow.

**Daily Tracker:** Dev A runs the tracker tonight.
**Active Phase:** Phase 0 | **State:** IN PROGRESS — critical bugs fixed, version pinning done

---

### DAY 3 — Wednesday, June 17 — Schema Keyword Warning (B14) + README Config Table (A4) + LangChain Fix (B15) + Infra Tests

**Theme:** The highest-leverage user-facing correctness item (B14) implemented by Dev A; Dev B closes the example defect (B15) and strengthens infrastructure test coverage.

---

#### DEV A — Task Focus: Schema Keyword Warning (B14) + README Config Table (A4)

**Files:** `domain/validator.py`, `README.md`
**Complexity:** MEDIUM | **Effort:** 6 hrs

---

**TASK A3.1: Implement the keyword warning in LocalValidator (B14)**

> *Start condition: Dev B's vocabulary gap list from Day 1 scratch/b14_keyword_gap.md.*

- Open `domain/validator.py`, specifically `LocalValidator._extract_params()` (line ~333).
- Create a module-level constant set:
  ```python
  _HANDLED_SCHEMA_KEYWORDS: frozenset[str] = frozenset({
      "required", "properties", "type", "enum",
      "minimum", "maximum", "min", "max",
      "pattern", "null_forbidden",
  })
  ```
- At the start of `_extract_params()` (or in a new pre-validation method called from `LocalValidator.validate()`),
  add a vocabulary audit:
  ```python
  @staticmethod
  def _warn_unhandled_keywords(schema: dict, logger: ILogger | None = None) -> None:
      """Emit a WARNING for any schema keyword that LocalValidator silently ignores
      when semantic validation is off. This prevents contracts that 'look enforced'
      but aren't. See 02_FAILURE_PATHS.md B14."""
      all_keywords = set(schema.keys())
      # Also check inside each property definition
      for prop_def in schema.get("properties", {}).values():
          if isinstance(prop_def, dict):
              all_keywords.update(prop_def.keys())
      unhandled = all_keywords - _HANDLED_SCHEMA_KEYWORDS - {"description", "title", "$schema"}
      if unhandled:
          msg = (
              f"Contract schema contains keyword(s) {unhandled} that LocalValidator does not enforce "
              f"when CONGINE_SEMANTIC_VALIDATION=false. These keywords are silently ignored. "
              f"Either enable semantic validation or remove these keywords from the contract."
          )
          if logger:
              logger.warning(msg)
          else:
              import warnings
              warnings.warn(msg, category=UserWarning, stacklevel=3)
  ```
- Call `_warn_unhandled_keywords(schema, self._logger)` from `LocalValidator.validate()` at the top,
  before the rule loop. This means the warning fires once per validation attempt (which is fine — it can be
  made into a one-time-per-contract-id warning later via a set of already-warned IDs, but for Phase 0, once
  per call is acceptable).
- **Alternatively (better for Phase 0):** call this warning during sync (in `SyncContractsUseCase._apply()`)
  rather than on every hot-path call. This is more correct — you know about the unhandled keywords when the
  contract is first loaded, not on every validation. If you go this route, add a parameter to `_apply()` to
  pass the logger through.
- Write a test in `tests/unit/test_validator.py`:
  ```python
  def test_warns_on_unhandled_keyword(caplog):
      schema = {"required": ["summary"], "properties": {
          "summary": {"type": "string", "minLength": 10}  # minLength is unhandled
      }}
      validator = LocalValidator()
      with caplog.at_level("WARNING"):
          validator.validate({"summary": "hi"}, schema)
      assert "minLength" in caplog.text
      assert "silently ignored" in caplog.text
  ```
- Commit: `fix(domain): warn on silently-ignored schema keywords when semantic validation is off (B14)`.

---

**TASK A3.2: Complete README config table (A4)**

> *Start condition: Dev B's scratch/a4_config_table_draft.md with the first 10 rows.*

- Open `README.md` and locate the config table.
- Open Dev B's draft from `scratch/a4_config_table_draft.md`.
- Continue filling remaining env vars by reading `config.py:from_env()`:
  `CONGINE_JSONSCHEMA_DRAFT`, `CONGINE_SEMANTIC_MAX_BREACHES`, `CONGINE_DRIFT_SAMPLE_LIMIT`,
  `CONGINE_MAX_SCHEMA_BYTES`, `CONGINE_MAX_CONTRACT_FILES`, `CONGINE_MAX_STREAM_BUFFER_CHARS`,
  `CONGINE_MAX_HTTP_RESPONSE_BYTES`, `CONGINE_LOG_REDACTION`, `CONGINE_CACHE_SWEEP_INTERVAL_SECONDS`.
- For each: add the field name, default value (from `config.py` field defaults), and a one-line description
  matching what `from_env()` does with it.
- Cross-check against `tests/unit/test_config_wiring.py` — every env var wired in that test should now
  appear in the README table.
- Commit: `docs(readme): complete config env-var reference table (A4)`.

**END criteria for Dev A Day 3:**
- B14 warning fires in tests.
- README config table has every env var from `from_env()`.
- `pytest tests/unit/test_validator.py -v` → green including the new warning test.

---

#### DEV B — Task Focus: LangChain Example Fix (B15) + Infrastructure Test Coverage

**Files:** `examples/LangChain/agent.py`, `examples/LangChain/contracts/return_processing.json`, `tests/unit/test_cache.py`, `tests/unit/test_event_bus.py`, `tests/unit/test_circuit_breaker.py`
**Complexity:** LOW (B15) + MEDIUM (tests) | **Effort:** 6 hrs

---

**TASK B3.1: Fix LangChain example offline fallback (B15)**

> *Start condition: nothing. Read the example and contract together.*

- Open `examples/LangChain/agent.py`. Find the offline fallback (line ~88):
  ```python
  action = "manual_review"  # This is the broken value
  ```
- Open `examples/LangChain/contracts/return_processing.json`. Read the `action` field's `enum` definition.
  It should be `["approve_return", "reject_return", "escalate"]`. The correct offline fallback is `"escalate"`.
- Fix `agent.py` line ~88: change `action = "manual_review"` to `action = "escalate"`.
- Also fix the Pydantic field description (in `agent.py`) that says `manual_review` in the enum description —
  update it to match the actual contract enum: `["approve_return", "reject_return", "escalate"]`.
- Test: run `python examples/LangChain/agent.py` without a `GOOGLE_API_KEY` set. It should now NOT raise
  on Scenario 1 (the "clean, compliant" path). It may still print a validation pass or envelope result.
- Commit: `fix(example): align offline fallback action enum to contract (B15)`.

---

**TASK B3.2: Strengthen test coverage — LFU Cache eviction (test_cache.py)**

> *Start condition: B3.1 committed.*

Read `tests/unit/test_cache.py`. Add the following tests if not already present:
1. `test_lfu_evicts_least_frequently_used()` — put 3 items in a cache of capacity 2, access one twice,
   confirm the least-accessed is evicted when a fourth is added.
2. `test_ttl_expired_entry_is_not_returned()` — put an entry with a 1ms TTL, sleep 5ms, `get()` → `None`.
3. `test_sweep_removes_expired_entries()` — put 3 entries with 1ms TTL, sleep 10ms, call `sweep_expired()`,
   assert `size() == 0`.
4. `test_concurrent_put_get_is_thread_safe()` — launch 20 threads alternately doing `put()` and `get()`
   on the same key with different values. Assert no exception and the final `get()` returns a valid value.
5. `test_version_keyed_entries_coexist()` — (new, for version pinning) put `"order_v1"` and `"order_v2"` as
   two separate keys, assert both coexist and return their respective schemas.
- Commit: `test(cache): comprehensive LFU eviction, TTL, thread-safety, and version-key tests`.

---

**TASK B3.3: Strengthen test coverage — QueueEventBus (test_event_bus.py)**

Read `tests/unit/test_event_bus.py`. Add:
1. `test_publish_increments_queue_depth()` — publish 5 events, assert `queue_depth() == 5` (before drain).
2. `test_dropped_total_increments_on_full_queue()` — set queue `maxsize=1`, publish 3 events, assert
   `dropped_total() >= 2` (the first event fills the queue; the second and third are dropped).
3. `test_drain_clears_queue()` — publish 3 events, let the drain worker run (sleep briefly), assert
   `queue_depth() == 0` (or close to it).
4. `test_noop_event_bus_discards_all()` — create a `NoOpEventBus`, publish 10 events, assert no exception
   and the bus has no state to inspect.
- Commit: `test(event_bus): queue depth, drop counting, drain, and NoOp behaviour`.

---

**TASK B3.4: Strengthen test coverage — CircuitBreaker (test_circuit_breaker.py)**

Read `tests/unit/test_circuit_breaker.py`. Verify these tests exist; add them if not:
1. `test_breaker_transitions_closed_to_open_after_failures()` — trip the breaker `failure_threshold` times,
   assert `state == OPEN` and `allow() == False`.
2. `test_half_open_only_allows_one_probe()` — open the breaker, advance clock past `recovery_timeout`,
   assert `allow() == True` once (probe), then `allow() == False` again (still half-open, no second probe).
3. `test_successful_probe_closes_breaker()` — open breaker → half-open → `record_success()` → assert `CLOSED`.
4. `test_failed_probe_reopens_breaker()` — open → half-open → `record_failure()` → assert `OPEN` again.
- Commit: `test(circuit_breaker): full state-machine transition coverage`.

**END criteria for Dev B Day 3:**
- B15 example fix committed and verified by running the example.
- Three new test files with combined 12+ new tests, all passing.
- `pytest tests/unit/test_cache.py tests/unit/test_event_bus.py tests/unit/test_circuit_breaker.py -v` → green.

---

#### END-OF-DAY SYNC — Day 3

1. Dev A demonstrates the B14 warning by running the example with `CONGINE_SEMANTIC_VALIDATION=false`
   (the default) against a contract with `minLength`. The warning should appear in logs.
2. Dev B confirms the LangChain example runs without raising (B15 fix verified live).
3. Both run `pytest -x -q` — all green.

**Daily Tracker:** Dev B runs tracker.
**Active Phase:** Phase 0 | **State:** IN PROGRESS — 8 of 14 items complete

---

### DAY 4 — Thursday, June 18 — Test Coverage Sprint (Domain + Adapter Tests)

**Theme:** Both developers write tests. No new features. The goal is to bring Phase 0 test coverage to the level where `pytest --tb=short -q` shows zero failures and high confidence.

---

#### DEV A — Task Focus: Domain + Use Case Test Coverage

**Files:** `tests/unit/test_validator.py`, `tests/unit/test_usecase.py`, `tests/adversarial/test_bounded_executor.py`, `tests/unit/test_sync_usecase.py`

**TASK A4.1: Complete RuleEngine unit tests (test_validator.py)**

For each of the 6 rules, ensure all of the following test cases exist:

**FIELD_PRESENCE rule:**
- `test_field_presence_pass()` — all required fields present → no breach
- `test_field_presence_missing_required_field()` — one missing → one BreachDetail with rule=FIELD_PRESENCE
- `test_field_presence_extra_fields_allowed()` — extra non-required fields → no breach
- `test_field_presence_empty_payload_with_required_fields()` → breaches for all required

**TYPE_MATCH rule:**
- `test_type_match_string()`, `test_type_match_int()`, `test_type_match_bool()`, `test_type_match_list()`,
  `test_type_match_nested_dict()` — all should pass when types match
- `test_type_match_wrong_type()` — int where string expected → BreachDetail with rule=TYPE_MATCH
- `test_type_match_null_when_not_nullable()` → breach

**ENUM_VALUES rule:**
- `test_enum_values_valid_value()` → no breach
- `test_enum_values_invalid_value()` → breach with `actual` and `expected` populated
- `test_enum_values_case_sensitive()` → "Foo" ≠ "foo" → breach

**RANGE_CHECK rule:**
- `test_range_check_within_bounds()` → no breach
- `test_range_check_below_minimum()`, `test_range_check_above_maximum()` → breaches
- `test_range_check_at_boundary_inclusive()` → at exact minimum/maximum → no breach

**NULL_GUARD rule:**
- `test_null_guard_null_when_forbidden()` → breach
- `test_null_guard_null_when_allowed()` → no breach
- `test_null_guard_missing_field_not_null_guard_issue()` → field_presence handles absence

**REGEX_PATTERN rule:**
- `test_regex_pattern_matches()` → no breach
- `test_regex_pattern_no_match()` → breach
- `test_regex_pattern_oversized_value_rejected()` → value over MAX_REGEX_VALUE_LENGTH → breach (not ReDoS)
- `test_regex_pattern_oversized_pattern_rejected()` → pattern over MAX_PATTERN_LENGTH → contract defect handled
- `test_regex_pattern_uses_re2()` — confirm via `type(re2.fullmatch(...))` is `re2.Match`

**TASK A4.2: Integration tests for version-pinned cache**

In `tests/integration/test_end_to_end.py`, add:
- `test_validate_with_explicit_version()` — full wired container, validate with `contract_version="v1"` and
  `contract_version="v2"` against two different schemas → assert correct schema was used.

**TASK A4.3: Adversarial tests for bounded executor (existing file expansion)**

In `tests/adversarial/test_bounded_executor.py`, verify these tests exist:
- `test_saturation_sheds_load()` — fill all slots, assert next request raises `TimeoutError` immediately.
- `test_timed_out_zombie_holds_capacity()` — submit a very slow callable, time out waiting for it,
  assert capacity is still occupied (slot count decrement hasn't happened yet).
- `test_async_saturation()` — async version of the saturation test.
- `test_re_entrancy_guard()` — call `run_with_timeout` from within a pool worker; assert it runs inline
  (re-entrancy guard).
- Add these if missing.

Commit: `test(domain): complete 6-rule RuleEngine unit tests + version-pinned integration + executor adversarial`

---

#### DEV B — Task Focus: Adapter + Guard + LangChain Test Coverage

**Files:** `tests/unit/test_guard.py`, `tests/unit/test_langchain_handler.py`, `tests/integration/test_end_to_end.py`

**TASK B4.1: Guard tests (test_guard.py)**

Add/verify:
1. `test_guard_with_explicit_container_passes()` — decorated fn returns valid output → result is envelope with validation_result.status == "pass".
2. `test_guard_with_no_container_raises_on_missing_schema()` — no bootstrap, first call → `CongineContractNotFoundError`.
3. `test_guard_mode_raise_on_breach()` — mode="raise" + invalid output → `CongineValidationError` raised.
4. `test_guard_mode_silent_on_breach()` — mode="silent" + invalid output → original output returned, no raise.
5. `test_guard_mode_degrade_on_breach()` — mode="degrade" + invalid output → envelope with `degraded=True`.
6. `test_guard_async_function()` — async decorated function → `execute_async` called → result correct.
7. `test_guard_with_extractor()` — custom `extractor=lambda r: r["data"]` → validation runs on extracted value.

**TASK B4.2: LangChain handler tests (test_langchain_handler.py)**

Add/verify:
1. `test_handler_validates_on_llm_end()` — mock LangChain `on_llm_end`, pass valid text → result stored in `handler.results`.
2. `test_handler_buffers_streaming_tokens()` — call `on_llm_new_token` 10 times, then `on_llm_end` → buffer concatenated.
3. `test_handler_truncates_oversized_buffer()` — stream tokens exceeding `MAX_STREAM_BUFFER_CHARS` → buffer truncated, no exception.
4. `test_handler_returns_none_on_non_congine_error()` — simulate a non-Congine error in validate → `None` returned (not re-raised).
5. `test_handler_result_keyed_by_run_id()` — two simultaneous LLM runs (different `run_id`) → results stored separately.

**TASK B4.3: Integration test updates for all Phase 0 fixes**

In `tests/integration/test_end_to_end.py`, add:
1. `test_full_path_passes_with_correct_output()` — sanity check end-to-end with wired container.
2. `test_strict_mode_raises_after_telemetry_publish()` — verify telemetry-before-raise ordering: exactly 1 event published before the raise.
3. `test_offline_mode_works_without_control_plane()` — use `FileContractRepository` + `NoOpEventBus` → validation works with zero network I/O.

Commit: `test(adapters): guard mode coverage, LangChain handler, integration end-to-end updates`

---

#### END-OF-DAY SYNC — Day 4

1. Run `pytest -x -q --tb=short` together.
2. Fix any test failures together (pair-program for 30 mins if needed).
3. Count test totals: aim for 80+ tests total across the suite by end of today.

**Daily Tracker:** Dev A runs tracker.
**Active Phase:** Phase 0 | **State:** NEARLY DONE — test coverage complete

---

### DAY 5 — Friday, June 19 — Quickstart + Phase 0 QA + Tag v0.1.1

**Theme:** Polish, quickstart, final QA, and ship Phase 0 as v0.1.1.

---

#### DEV A — Task Focus: 5-Minute Quickstart + Phase 0 Documentation Polish

**Files:** `QUICKSTART.md` (new), `README.md`

**TASK A5.1: Write QUICKSTART.md**

The Builder's Codex is explicit: "if a developer can't integrate Congine in 5 minutes, you don't have a product yet." Write a QUICKSTART.md that a developer with zero prior Congine knowledge can follow in 5 minutes and see a validation pass AND a validation breach:

```markdown
# Congine 5-Minute Quickstart

## 1. Install
pip install congine

## 2. Create a contract (contracts/my_contract.json)
{
  "required": ["status", "confidence"],
  "properties": {
    "status": {"type": "string", "enum": ["pass", "fail", "pending"]},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
  }
}

## 3. Guard your LLM function
from congine import ServiceContainer, congine_guard

container = ServiceContainer.from_env()
container.bootstrap()

@congine_guard("my_contract", container=container)
def classify(text: str) -> dict:
    return {"status": "pass", "confidence": 0.95}  # your LLM call here

result = classify("Some input")
print(result)  # {"output": {...}, "validation_result": ValidationResult(status='pass', ...)}

## 4. See a breach
@congine_guard("my_contract", container=container, mode="raise")
def classify_bad(text: str) -> dict:
    return {"status": "unknown", "confidence": 1.5}  # invalid!

classify_bad("input")  # raises CongineValidationError with breach details
```

Include environment variable setup (`CONGINE_BASE_URL`, `CONGINE_API_KEY`, or offline mode with
`CONGINE_LOCAL_CONTRACTS_DIR`). Add a troubleshooting section for the two most common errors:
`CongineContractNotFoundError` (forgot to call `bootstrap()`) and `CongineConfigurationError`
(missing env vars). Keep it to one page.

**TASK A5.2: Update README for Phase 0 changes**

- Add a note about the version-pinned cache key: `@congine_guard("contract_id", version="v1")`.
- Add a note in the config table section pointing to the complete table (completed on Day 3).
- Add a "Known Limitations (Phase 0)" section listing what is out of scope: distributed state,
  durable telemetry, RBAC, MCP — and when each will arrive.
- Commit: `docs: add QUICKSTART.md + README Phase 0 polish and known-limitations section`.

---

#### DEV B — Task Focus: Full Test Suite QA + Phase 0 Closure

**TASK B5.1: Full test suite run and failure investigation**

- Run `pytest -x -q --tb=long 2>&1 | tee test_results.txt`.
- For every failure, investigate and fix (within Dev B's layer — if a domain test fails, flag to Dev A).
- Target: 0 failures.
- Run with `--cov=congine_core --cov-report=term-missing` to see coverage gaps.
- Identify any uncovered lines in the critical hot-path files:
  `validate_contract_usecase.py`, `lfu_cache.py`, `bounded_executor.py`, `dependency_injection.py`.
  For each uncovered path, write a quick test.

**TASK B5.2: Phase 0 code review**

- Review Dev A's B9 fix (`dependency_injection.py`) for correctness: does the ref counting logic have any race
  conditions? Check that the `_tenant_lock` is always held when modifying `_ref_count`.
- Review the version-pinning key scheme: is `"{contract_id}@{version}"` robust? Could a contract_id or version
  string contain `@`? If yes, add a validation in `config.py` or `CongineConfig.__post_init__`.
- Review the B14 keyword warning: is it firing at the right time (sync vs hot path)?
- Leave inline review comments in a PR description.

**TASK B5.3: Git tag v0.1.1 and update CHANGELOG**

- Update `CHANGELOG.md`: move the FIX-01..FIX-14 items from `[Unreleased]` to `[0.1.1] - 2026-06-19`.
  Add entries for the new Phase 0 fixes: B9, B10, B11, B6, A1, A2, A3, A6, B14, B15, timer cleanup.
- Update `pyproject.toml` version from `0.1.0` to `0.1.1`.
- Tag: `git tag -a v0.1.1 -m "Phase 0 complete: all hardening fixes, test coverage, and quickstart"`.
- Push: `git push --tags`.
- Commit: `chore(release): version bump to 0.1.1, Phase 0 complete`.

---

#### END-OF-DAY SYNC — Day 5 (JOINT)

Both developers run the full suite together. This is the Phase 0 acceptance test:

```bash
pytest -x -q --tb=short
# Expected: 0 failures, 80+ tests
python examples/LangChain/agent.py  # Expected: no raise on Scenario 1
# Set CONGINE_SEMANTIC_VALIDATION=false and run with a minLength contract → warning in logs (B14)
# Check git tag: git log --oneline -5
```

Run the Document 2 deep-analysis prompt in Claude Code to refresh `CONGINE_PROGRESS.md` with Phase 0 as complete.

**Daily Tracker:** Both update tracker together. Phase 0 state → **DONE**.

---

## SECTION 2 — PHASE 1A (MCP SERVER) + PHASE 1B (SQLITE) IN PARALLEL
### Week 2 | June 22–26, 2026 | Goal: MCP server connected to Claude Code/Cursor + durable SQLite telemetry

**Key principle this week:** Dev A and Dev B are on completely independent parallel tracks. Dev A builds the MCP
server (new L4 infrastructure + L3 use case surface). Dev B builds the SQLite event bus (new L4 infrastructure
+ L3 use case). They share only the L1 port (`IEventBus` already exists) and the `ValidationEvent` model
which will be added to `domain/models.py` (Dev B's first task on Day 7).

---

### DAY 6 — Monday, June 22 — MCP Server Foundation + SQLite Event Bus Foundation

---

#### DEV A — Task Focus: MCP Server Architecture + CongineServer Base Class

**Files (new):** `src/congine_core/mcp/__init__.py`, `src/congine_core/mcp/server.py`
**Files (touch):** `ports/mcp_transport.py` (new port), `pyproject.toml`

**TASK A6.1: Study the MCP protocol**

Before writing a line, spend 1 hour:
- Read the MCP Python library documentation (install `mcp` package: `pip install mcp`).
- Understand the `FastMCP` or `MCPServer` class, `@tool` decorator pattern, and transport types
  (stdio for local dev, HTTP/SSE for cloud).
- Read Claude Code's MCP configuration format:
  ```json
  {
    "mcpServers": {
      "congine": {
        "command": "python",
        "args": ["-m", "congine_core.mcp.server"],
        "env": {"CONGINE_BASE_URL": "...", "CONGINE_API_KEY": "..."}
      }
    }
  }
  ```
- Understand what happens end-to-end: Claude Code starts the MCP server as a subprocess, communicates
  over stdin/stdout (stdio transport), and can call tools in the server's reasoning loop.

**TASK A6.2: Define the MCP transport port**

Create `ports/mcp_transport.py`:
```python
from typing import Protocol, Any

class IMCPTransport(Protocol):
    """Seam for MCP transport (stdio vs HTTP/SSE).
    Concrete implementations live in infrastructure/mcp_stdio_transport.py
    and infrastructure/mcp_http_transport.py (Phase 1A).
    """
    async def start(self, server: Any) -> None: ...
    async def stop(self) -> None: ...
```
This keeps the MCP transport swappable (stdio for local, HTTP/SSE for cloud) without touching the server logic.

**TASK A6.3: Create the CongineServer class skeleton**

Create `src/congine_core/mcp/server.py`:
```python
"""
Congine MCP Server — exposes Congine validation as MCP tools for Claude Code / Cursor.

Start it:
  python -m congine_core.mcp.server            # stdio (local dev)
  CONGINE_MCP_TRANSPORT=http python -m ...     # HTTP/SSE (cloud)
"""
from mcp import FastMCP
from congine_core.adapters.dependency_injection import ServiceContainer

app = FastMCP("congine")

@app.tool()
async def validate_output(output: dict, contract_id: str, contract_version: str = "latest") -> dict:
    """Validate a dict output against a Congine JSON contract. Returns pass/fail + breach details."""
    ...  # Day 7 implementation

@app.tool()
async def validate_code_change(files_changed: list[str], contract_id: str) -> dict:
    """Validate a set of changed files against an architectural contract."""
    ...  # Day 8 implementation

@app.tool()
async def get_project_contracts() -> dict:
    """List all contracts available in this project's contracts directory."""
    ...  # Day 7 implementation

if __name__ == "__main__":
    app.run()   # defaults to stdio transport
```

Create `src/congine_core/mcp/__init__.py` with `__all__ = ["app"]`.

Add `[mcp]` optional dependency to `pyproject.toml`:
```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0"]
```

Commit: `feat(mcp): scaffold CongineServer with FastMCP; add mcp transport port and [mcp] extra`

---

#### DEV B — Task Focus: SqliteEventBus Foundation + DB Schema Design

**Files (new):** `src/congine_core/infrastructure/sqlite_event_bus.py`
**Files (touch):** `domain/models.py` (study only today — Day 7 for actual edit)

**TASK B6.1: Study IEventBus and existing QueueEventBus**

- Read `ports/event_bus.py` (the `IEventBus` Protocol: `publish(event: TelemetryEvent) → None`).
- Read `infrastructure/queue_event_bus.py` completely: understand its `_queue`, `_drain_worker`, batch
  POST logic, `_dropped_total`, `stop()` method.
- Read `domain/models.py:TelemetryEvent` completely — every field.
- Write in your notes: "What SqliteEventBus needs to implement from IEventBus" and "What new fields
  the ValidationEvent model needs vs TelemetryEvent."

**TASK B6.2: Design the SQLite schema**

Design the events table. Write it as SQL first:
```sql
CREATE TABLE IF NOT EXISTS validation_events (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,          -- ISO 8601
    project_id TEXT NOT NULL,
    tenant_id TEXT,
    contract_id TEXT NOT NULL,
    contract_version TEXT,
    payload_hash TEXT,                -- SHA-256 of payload
    status TEXT NOT NULL,             -- 'pass' | 'fail' | 'degraded'
    degraded INTEGER DEFAULT 0,       -- 0 or 1
    breach_count INTEGER DEFAULT 0,
    breach_details_json TEXT,         -- JSON array of BreachDetail dicts
    duration_ms REAL,
    agent_id TEXT,                    -- which coding agent triggered this
    file_paths_json TEXT,             -- JSON array of file paths
    git_commit_sha TEXT,
    session_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_project_contract
    ON validation_events(project_id, contract_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_events_project_file
    ON validation_events(project_id, timestamp DESC);
```
Store this SQL in a constant in `sqlite_event_bus.py`. Use WAL mode: `PRAGMA journal_mode=WAL`.

**TASK B6.3: Implement SqliteEventBus.__init__ and publish()**

```python
import sqlite3, json, hashlib, pathlib
from congine_core.domain.models import TelemetryEvent
from congine_core.ports.logger import ILogger

class SqliteEventBus:
    """IEventBus implementation that persists events to SQLite in WAL mode.
    Selected when CONGINE_EVENT_STORE=sqlite. Falls back to QueueEventBus by default.
    """
    def __init__(self, db_path: pathlib.Path, logger: ILogger):
        self._db_path = db_path
        self._logger = logger
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    def publish(self, event: TelemetryEvent) -> None:
        """Persist the event synchronously. Non-blocking from the hot path is
        maintained by the container running this in a background thread if needed."""
        try:
            self._conn.execute(_INSERT_SQL, self._to_row(event))
            self._conn.commit()
        except Exception as e:
            self._logger.error(f"SqliteEventBus: failed to persist event: {e}")

    def _to_row(self, event: TelemetryEvent) -> tuple:
        ...  # map TelemetryEvent fields to the SQL row tuple
```

Commit: `feat(infra): SqliteEventBus skeleton with WAL-mode schema and publish()`

---

#### END-OF-DAY SYNC — Day 6

- Both commit and push.
- Dev A shares the MCP tool schema (the 3 tool signatures) with Dev B → Dev B confirms the `publish()` in
  SqliteEventBus can store enough data to answer MCP history queries.
- Check: does `ValidationEvent` need a new model or can we extend `TelemetryEvent`? Decision: **extend by
  adding optional fields to TelemetryEvent** (backward compatible). Dev B implements this on Day 7.

---

### DAY 7 — Tuesday, June 23 — MCP Tools + ValidationEvent Model

*(Day 7 through Day 10 follow the same detailed structure. Full day-by-day breakdown continues similarly.)*

**Dev A:** Implements `validate_output` and `get_project_contracts` MCP tools (full implementation body),
stdio transport wiring, and unit tests using an `MCP TestClient`.

**Dev B:** Extends `domain/models.py` to add `project_id`, `agent_id`, `file_paths`, `git_commit_sha`,
`session_id` optional fields to `TelemetryEvent` with `None` defaults (fully backward-compatible). Implements
`SqliteEventBus` query methods: `get_events_by_project()`, `get_events_by_file()`.

---

### DAY 8 — Wednesday, June 24 — validate_code_change MCP Tool + HistoryQueryUseCase

**Dev A:** Implements `validate_code_change` MCP tool body + HTTP/SSE transport implementation.

**Dev B:** Creates `usecases/history_query_usecase.py` with `get_violation_history(project_id, file_paths, limit)`.
Wires `SqliteEventBus` into `dependency_injection.py` behind `CONGINE_EVENT_STORE=sqlite` config toggle
(4-touch rule: config.py knob + README table entry + test + DI wiring).

---

### DAY 9 — Thursday, June 25 — MCP Tests + Phase 1B Tests

**Dev A:** Full MCP server test suite. MCP configuration guide (`.mcp.json` format for Claude Code + Cursor).
System prompt template that instructs coding agents to call `validate_code_change` before applying changes.

**Dev B:** Full `SqliteEventBus` test suite including restart-survival test (write events, close DB,
re-open, assert events still there). Document `ValidationEvent` schema + `CONGINE_EVENT_STORE` config.

---

### DAY 10 — Friday, June 26 — Phase 1A/1B Integration + Tag v0.2.0-sqlite

**Both devs:** Cross-review, integration test (MCP server calls history query via SqliteEventBus),
merge, push, and tag `v0.2.0-sqlite`. Run Document 2 deep analysis to refresh CONGINE_PROGRESS.md.

---

## SECTION 3 — PHASE 1A PART 2 (CLI + GIT HOOKS) + PHASE 1C (TEACH) IN PARALLEL
### Week 3 | June 29 – July 3, 2026 | Goal: `congine validate-diff` CLI + correction_hint in BreachDetail

---

### DAYS 11–15 (June 29 – July 3)

**Dev A (Days 11–13):** CLI foundation (`cli/main.py`, `typer` commands), `diff_parser.py` to parse
`git diff --cached` output and map hunks to contract IDs, `install-hook` command, GitHub Actions
`action.yml` for the `congine/validate-action@v1` gate. Full CLI test suite + git hook documentation.

**Dev B (Days 11–13):** `correction_hint: str` + `token_cost_to_fix: int` added to `BreachDetail`
frozen dataclass (domain/models.py), table-driven correction hint generator in RuleEngine per rule type
(e.g., TYPE_MATCH → "Field '{field}' expected type {expected}, got {actual}. Cast or coerce the value."),
agent-readable `ValidationResult.to_agent_format()` serialization, MCP surface update to include hints.

**Day 14 (July 2):** Both write tests for their Phase 1C/CLI work independently.

**Day 15 (July 3, Joint):** Full Phase 1 integration test. End-to-end: git pre-commit hook triggers
`congine validate-diff` → catches breach → returns `correction_hint` → history logged to SQLite →
MCP surfaces history. Tag `v0.2.0`. Re-run Document 2 deep analysis.

---

## SECTION 4 — PHASE 2: INTELLIGENCE LAYER
### Week 4 | July 6–10, 2026 | Goal: Architecture graph + pattern detection + Phase 2 MCP tools

---

### DAYS 16–20 (July 6–10)

**Dev A (Days 16–19):** `domain/arch_graph.py` with `ArchNode`, `ArchEdge`, `ArchGraph` domain models.
`usecases/validate_arch_usecase.py` with layer boundary checking and `ArchViolation` model. Enhancement
of `validate_code_change` MCP tool to return `ArchViolation`s. New MCP tools: `get_arch_violations()`,
`get_violation_patterns()`.

**Dev B (Days 16–19):** `usecases/pattern_detection_usecase.py` with violation clustering (contract ×
field × rule frequency grouping). Extension of SQLite schema to store `ArchNode` and `ArchEdge` tables.
Hook into `ValidateContractUseCase._finalize()` to update the graph on every validation (via the event bus).
Phase 2 test suite including: "20 violations of the same rule → pattern detected" integration test.

**Day 20 (July 10, Joint):** Full Phase 2 integration. Full test suite (Phase 0 + 1A + 1B + 1C + 2).
Code review. Merge. Re-run Document 2 deep analysis. Tag `v0.3.0`. Plan Phase 3 (Redis, RBAC, OpenTelemetry).

---

## SECTION 5 — COORDINATION PROTOCOL

### 5.1 Daily Rhythm

| Time | Activity |
|------|----------|
| Start of day | 15-min sync: review yesterday's daily tracker entry, clarify today's tasks |
| End of day | Both push commits; rotating dev runs daily tracker prompt |
| Friday | Joint session: cross-review, integration test, merge all branches |

### 5.2 Branch Strategy

| Branch | Owner | Lifecycle |
|--------|-------|-----------|
| `main` | Both | Protected; merge only via PR |
| `phase0/eviction-fix` | Dev A | Day 1-2; merge on Day 5 |
| `phase0/small-fixes` | Dev B | Days 1-3; merge on Day 5 |
| `phase1a/mcp-server` | Dev A | Days 6-10; merge on Day 10 |
| `phase1b/sqlite-bus` | Dev B | Days 6-10; merge on Day 10 |
| `phase1c/correction-hints` | Dev B | Days 11-15; merge on Day 15 |
| `phase1a2/cli-hooks` | Dev A | Days 11-15; merge on Day 15 |
| `phase2/arch-graph` | Dev A | Days 16-20; merge on Day 20 |
| `phase2/pattern-detection` | Dev B | Days 16-20; merge on Day 20 |

**Rule:** Never commit directly to `main`. Every branch ends with a PR that the other developer reviews.

### 5.3 Conflict Resolution Protocol

Given the track assignment (Dev A = domain/use cases; Dev B = infrastructure/adapters), merge conflicts
will be rare. The two most likely conflict locations are:

1. **`domain/models.py`:** Both devs may add fields. Resolve by: Dev B always adds ValidationEvent fields;
   Dev A always adds validation-logic-related fields (like `correction_hint` is on `BreachDetail` which
   is in the domain). If both need to edit `domain/models.py` on the same day, Dev A makes the edit and
   Dev B pulls before committing.
2. **`dependency_injection.py`:** Dev B owns this file for wiring. If Dev A needs a new dependency wired,
   Dev A defines the port and documents the concrete to wire; Dev B does the wiring commit.

### 5.4 Daily Tracker Usage

The Document 3 daily tracker must be run at end of every day. The rotating schedule:
- Mon/Wed/Fri: Dev A runs tracker
- Tue/Thu: Dev B runs tracker

The tracker appends to `CONGINE_PROGRESS.md:DAILY LOG`. After running it, both devs should read the
"What you COULD do next" section and confirm it matches tomorrow's plan in this document.

---

## SECTION 6 — PHASE COMPLETION CHECKLIST

### Phase 0 Done ✓ (End of Day 5 / June 19)
- [ ] B9: Multi-tenant eviction is refcount/idle-safe with direct test
- [ ] A1: `requires-python = ">=3.10"` consistent across all files
- [ ] B14: WARNING fires for unenforced schema keywords when semantic=off
- [ ] B15: LangChain example runs clean on Scenario 1 without API key
- [ ] B10: Size bounds count UTF-8 bytes
- [ ] B11: CompositeValidator short-circuits on non-dict
- [ ] B6: `pii_sanitize` uses `re2`
- [ ] A6: TelemetryEvent docstring corrected
- [ ] A2/A3: ARCHITECTURE.md updated (ports/ rename + 6-tier count)
- [ ] A5: CHANGELOG FIX-12 gap noted
- [ ] Contract version pinning: cache key is `"{contract_id}@{version}"`
- [ ] `test_container.py`: 6 tests covering bootstrap, health, drift, reset, multi-tenant
- [ ] RuleEngine: complete unit tests for all 6 rules
- [ ] QUICKSTART.md: 5-minute guide exists and works
- [ ] README: complete config env-var table + Phase 0 known limitations
- [ ] Git tag: `v0.1.1`
- [ ] `pytest -x -q` → 0 failures, 80+ tests

### Phase 1A Done (End of Day 15 / July 3)
- [ ] `validate_output` MCP tool works against Claude Code
- [ ] `validate_code_change` MCP tool works
- [ ] `get_project_contracts` MCP tool works
- [ ] stdio transport connects to Claude Code / Cursor
- [ ] `congine validate-diff --stdin --contracts-dir` CLI exits 0/1
- [ ] `congine install-hook` installs a working pre-commit hook
- [ ] `congine/validate-action@v1` GitHub Action works in a test repo
- [ ] MCP configuration guide written

### Phase 1B Done (End of Day 15 / July 3)
- [ ] Events survive process restart (SQLite WAL)
- [ ] `get_violation_history(project_id, file_paths)` returns correct events
- [ ] `CONGINE_EVENT_STORE=sqlite` wires SqliteEventBus
- [ ] All 5 new `ValidationEvent` fields present: project_id, agent_id, file_paths, git_commit_sha, session_id

### Phase 1C Done (End of Day 15 / July 3)
- [ ] `BreachDetail.correction_hint` is populated for all 6 rule types
- [ ] `BreachDetail.token_cost_to_fix` has a reasonable estimate
- [ ] `ValidationResult.to_agent_format()` returns agent-readable dict
- [ ] MCP `validate_output` includes `correction_hints[]` in response

### Phase 2 Done (End of Day 20 / July 10)
- [ ] Recurring `(contract, field, rule)` clusters are queryable
- [ ] Per-file hotspots identified from violation history
- [ ] `validate_code_change` returns `ArchViolation`s for architectural contract breaches
- [ ] New MCP tools: `get_arch_violations()`, `get_violation_patterns()`
- [ ] Git tag: `v0.3.0`
