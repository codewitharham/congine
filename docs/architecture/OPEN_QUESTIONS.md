# Open questions — decisions & implementation record

Companion to `ARCHITECTURE_CURRENT.md` §17. Twelve questions, each rewritten as a
plain-language decision, with **the option you chose marked and what shipped for it**.

> **Status: all twelve answered and implemented — 2026-08-09.**
> Test suite: **350 passed, 1 skipped** (was 293/1). Ruff format + check clean.
> Audit-ID trail: `docs/architecture/AUDIT_ID_INDEX.md`.

## Decision summary

| # | Question | Chosen | Status |
|---|---|---|---|
| **Q1** | `region` does nothing | **B — wire it to a regional default `base_url`** | ✅ implemented |
| **Q2** | Union `type` silently breaks the contract | **A — support it** | ✅ implemented |
| **Q3** | `null_forbidden` isn't real JSON Schema | **A — keep it, document it loudly** | ✅ implemented |
| **Q4** | Keyword-scan misses future loaders | **C — documented required step + test** | ✅ implemented |
| **Q5** | Evicted containers leak threads | **A — arm cleanup at construction** | ✅ implemented |
| **Q6** | Python floor 3.10 or 3.11 | **A — 3.11 everywhere** | ✅ implemented |
| **Q7** | README documents 27 of 46 settings | **A + B — fill in *and* automate** | ✅ implemented |
| **Q8** | Ports under-declare their surface | **B — separate lifecycle interface** | ✅ implemented |
| **Q9** | Telemetry: best-effort or durable? | **A — keep both, config-selected** | ✅ decision recorded (no code change today) |
| **Q10** | Guard re-reads the env every call | **C — fix it *and* document** | ✅ implemented |
| **Q11** | One setting caps two limits | **A — split it** | ✅ implemented |
| **Q12** | Maintain the audit-ID trail? | **A — maintain it** | ✅ implemented |

**One thing needs your confirmation:** the regional hostnames chosen for Q1
(`https://api.{us,eu,apac}.congine.dev`) are placeholders — see Q1 below.

---

# Group A — "Does the contract actually enforce what the user wrote?"

## Q2 — A normal JSON Schema shape silently breaks the whole contract

**Was true.** `{"type": ["string", "null"]}` — the idiomatic nullable field —
crashed the rule engine internally on every validation, returning "fail,
degraded, zero breaches" with only a warning line under the default mode.

| Option | | |
|---|---|---|
| **A. Support it** | ✅ **CHOSEN** | Type check accepts a list — matches if any member matches |
| B. Reject loudly at load | | Safe, but rejects valid JSON Schema |
| C. Leave it | | Not defensible |

**What shipped**

- `_type_matches` now recurses over a union and returns true if any member
  matches ([domain/validator.py](libs/congine-sdk/src/congine_core/domain/validator.py)).
- `"null"` added to `_JSON_TYPE_MAP`, so `["string","null"]` is meaningfully
  enforced rather than matching everything.
- Empty unions and unions containing an unrecognised name are treated as
  unevaluable — and are still reported by the load-time warning.
- Breach messages render a union as `'string|null'`, not a Python list repr
  (`_type_label`).
- The vocabulary mirror tracks both changes; the existing anti-drift test
  (`RECOGNISED_TYPE_NAMES == frozenset(_JSON_TYPE_MAP)`) keeps them in step.

**Verified:** union + `"x"` passes · union + `None` passes · union + `5` fails
with one clean breach · `["boolean","number"]` + `True` passes ·
`["number","integer"]` + `True` still fails (bool is not a number).

---

## Q3 — `null_forbidden` is a Congine-only keyword

| Option | | |
|---|---|---|
| **A. Keep it, document it loudly** | ✅ **CHOSEN** | "JSON Schema plus one extension" |
| B. Drop it | | |
| C. Keep both | | |

**What shipped.** `RuleEngine.NULL_GUARD`'s docstring now states plainly that
`null_forbidden` is a Congine extension, that a contract using it is no longer a
portable JSON Schema document, and that Congine's *own* semantic validator
ignores it even with `CONGINE_SEMANTIC_VALIDATION=true`. It points readers at the
portable spelling — which Q2 just made available — and documents that, unlike
`required`, it does **not** support dot-notation.

**Note.** Because you also took Q2 = A, users now have both spellings. The
documentation recommends the portable one without removing the extension, so
nothing existing breaks.

---

## Q4 — The "your contract keyword does nothing" warning only fires on one path

| Option | | |
|---|---|---|
| A. Leave it in L3 | | Someone will forget |
| B. Move into the cache's `put()` | | Covers everything, slightly impure |
| **C. Documented required step + test** | ✅ **CHOSEN** | |

**What shipped**

- `find_unenforced_keywords` is now exported from `congine_core.domain` as the
  public helper, flagged in `__all__` as a required call.
- Its module docstring states the rule: **any code path that writes a schema into
  `ISchemaStorage` must run the scan and surface the result.**
- The rule is *enforced*, not just written down:
  `test_every_schema_writer_scans_for_unenforced_keywords` walks the real source
  tree with `ast` and fails when a new 3-argument `.put(id, schema, ttl)` call
  site appears in a module that doesn't reference the scan.
- A second test guards the guard — it proves the detector actually fires on an
  unscanned loader, so a broken detector can't pass silently.
- The convention is recorded in `.claude/CLAUDE.md`.

> This is the option that relies on discipline. The test converts it into a
> mechanical check, which is why C is defensible here — but if you later add
> several loaders at once, revisit B.

---

# Group B — "Does the configuration tell the truth?"

## Q1 — `region` is a setting that does absolutely nothing

| Option | | |
|---|---|---|
| A. Delete it | | |
| **B. Wire it to a default URL** | ✅ **CHOSEN** | `region=eu` picks the Frankfurt `base_url` |
| C. Send it as a header | | |
| D. Keep, mark "reserved" | | |

**What shipped**

- `_REGION_BASE_URLS` in `config.py` maps each region to its control-plane URL,
  exposed as `Region.default_base_url`.
- `CongineConfig.base_url_from_env()` applies a strict precedence:
  **explicit `CONGINE_BASE_URL` wins → else an explicitly-set `CONGINE_REGION`
  selects its regional endpoint → else the loopback default.**
- Local development is unaffected: setting neither still yields
  `http://localhost:8080`, so no existing test or workflow changed.

**Verified:** nothing set → `http://localhost:8080` · `REGION=eu` →
`https://api.eu.congine.dev` · `REGION=apac` + explicit URL → the explicit URL.

> ⚠️ **Needs your confirmation.** The hostnames
> (`https://api.{us,eu,apac}.congine.dev`) are placeholders — no real control-plane
> domain exists in this repository, and I did not want to invent one silently.
> They are isolated in a single constant with an `.. important::` note. Tell me
> the real endpoints and it's a one-line change per region.

---

## Q7 — The README documents 27 of 46 settings

| Option | | |
|---|---|---|
| **A. Fill in the missing rows** | ✅ **CHOSEN** | |
| **B. Test that fails on an undocumented field** | ✅ **CHOSEN** | |
| C. Generate the table | | |

**What shipped**

- The config table now documents **all 47 fields** (46 + the new one from Q11),
  generated from `dataclasses.fields(CongineConfig)` so nothing was missed.
  Descriptions call out the traps found during the review — the standalone
  switch's empty-string behaviour, the fail-closed dialect, the D-statistic vs
  p-value distinction, and `start_background_services` *not* being an offline
  switch.
- Two explanatory notes were added below the table: why the size budgets are
  conservative rather than permissive, and how the two size knobs now differ.
- `tests/unit/test_readme_config_table.py` fails in **four** directions: a field
  with no row, a row for a field that no longer exists, a row naming a variable
  `config.py` never reads, and a row whose field/variable pairing doesn't match
  `from_env()`. The last is parametrised, so failures name the exact field.

---

## Q11 — One setting secretly controls two unrelated limits

| Option | | |
|---|---|---|
| **A. Split into two settings** | ✅ **CHOSEN** | |
| B. Document the coupling | | |

**What shipped.** New `max_contract_file_bytes` field +
`CONGINE_MAX_CONTRACT_FILE_BYTES` + `DEFAULT_MAX_CONTRACT_FILE_BYTES`, wired to
`FileContractRepository(max_file_bytes=…)`. `max_schema_bytes` now bounds only the
cached schema on the hot path. Both default to 1 MiB, so behaviour is unchanged
until someone tunes one. Both documented, with the distinction spelled out.

**Verified:** `CONGINE_MAX_CONTRACT_FILE_BYTES=4096` moves the file cap and leaves
`max_schema_bytes` at its default.

---

# Group C — "Does the process behave itself over time?"

## Q5 — Should an evicted tenant container keep running forever?

| Option | | |
|---|---|---|
| **A. Arm cleanup at construction** | ✅ **CHOSEN** | |
| B. Leave it, document it | | |
| C. Refuse eviction while referenced | | |

**What shipped.** `_arm_deferred_teardown()` is now the last statement of
`__init__`, so **every** container self-cleans when it becomes unreferenced —
closing the second, quieter gap where a container that was never registered,
never evicted and never closed armed no cleanup at all. The eviction-time call is
retained as an idempotent no-op because that is where the guarantee matters.

**Three tests added/rewritten:**

- `test_plain_container_arms_teardown_at_construction` — a never-registered
  container tears down when dropped.
- `test_teardown_is_bounded_and_error_suppressing` — asserts `drain=False`,
  `wait=False`, and that one raising component doesn't stop the others.
- `test_evicted_unreferenced_container_is_torn_down` — rewritten to observe the
  container's *real* components (the finalizer now captures construction-time
  components, so swapping `container.event_bus` afterwards is no longer visible
  to it — a behaviour worth knowing).

---

## Q10 — The convenience path re-reads all 46 environment variables on every call

| Option | | |
|---|---|---|
| A. Fix the lookup order | | |
| B. Document as non-production | | |
| **C. Both** | ✅ **CHOSEN** | |

**What shipped**

- New `CongineConfig.deployment_mode_from_env()` reads **one** variable.
- `get_default()` now does the cheap topology probe, then returns the cached
  singleton; the full `from_env()` parse happens **once**, at construction.
- Semantics are preserved exactly: the mode is still re-read from the environment
  on every call, so flipping `CONGINE_DEPLOYMENT_MODE` still disables the shared
  singleton immediately, even after one has been built.
- The docstring explains why this is on the hot path and still recommends an
  explicit `container=` for production.

**Verified:** three `get_default()` calls → **one** `from_env()` call, same
instance returned; the multi-tenant guard still raises.

---

## Q6 — Is the minimum Python version 3.10 or 3.11?

| Option | | |
|---|---|---|
| **A. 3.11 everywhere** | ✅ **CHOSEN** | |
| B. 3.10 everywhere | | |

**What shipped.** All four sources of truth now agree: `requires-python = ">=3.11"`
(unchanged), the 3.10 classifier removed, ruff `target-version = "py311"`, and the
CI matrix reduced to `['3.11','3.12','3.13']`. `PYTHON_MIN_VERSION` in CI moved to
`3.11`. The misleading comment claiming 3.10 was "the declared floor" is gone, and
`.claude/CLAUDE.md` now names all four places that must stay in step.

> Worth knowing: the CI 3.10 leg could never have passed — `requires-python`
> already forbade it, so `uv` couldn't resolve the package there.

---

# Group D — "What shape should the next phase take?"

## Q8 — The extension points don't declare everything an extension needs

| Option | | |
|---|---|---|
| A. Add methods to each interface | | |
| **B. Separate small lifecycle interface** | ✅ **CHOSEN** | |
| C. Just document it | | |

**What shipped.** New `ports/lifecycle.py` with two composable protocols:

- `IStoppable` — `stop()`, with the obligations spelled out (idempotent, never
  raises, bounded — it runs from `atexit` and from a GC finalizer).
- `IObservable` — `health()`, required to be cheap, non-blocking and JSON-safe.

Composed where the signatures align: `ISchemaStorage(IStoppable, …)` plus a
declared `size()`; `IValidationRunner(IObservable, …)` plus a declared
`shutdown(wait)`. `IEventBus` declares its own widened `stop(drain=…)` and
`queue_depth()` rather than inheriting, because bus teardown takes an argument.

`dropped_total` is deliberately **not** declared as a protocol method — a Protocol
member is mandatory under `runtime_checkable`, and this one genuinely is optional
(the container probes it with `getattr`). It's documented in a comment at the
point where a reader would look for it.

Both protocols are exported from `congine_core.ports` and the package `__all__`.
The test doubles were brought up to the newly-declared contracts.

---

## Q9 — Is telemetry meant to be reliable, or best-effort?

| Option | | |
|---|---|---|
| **A. Keep both** | ✅ **CHOSEN** | Fire-and-forget default; durable store as a second implementation, config-selected |
| B. Durability by default | | |
| C. Write to both | | |

**What shipped — and what deliberately did not.** This is a *directional*
decision, so no behaviour changed today. What changed is that the decision is now
recorded where an implementer will actually encounter it: `IEventBus`'s docstring
states that the default bus is deliberately lossy, that this will not change, and
that durability arrives as a **second implementation of the same port**, selected
by config, never by making the default bus blocking — with the constraint that
`publish` must stay non-blocking (enqueue on the caller's thread, write from a
worker).

Q8 was its prerequisite and is now done, so a `SqliteEventBus` can be written
against a port that tells the whole truth.

> **Not built:** the SQLite event store itself, `HistoryQueryUseCase`, and the
> extended `TelemetryEvent` fields. Those are Phase C features, not answers to
> this question. Say the word and I'll build them.

---

## Q12 — Do you keep maintaining the audit-ID trail?

| Option | | |
|---|---|---|
| **A. Maintain it** | ✅ **CHOSEN** | Backfill + make annotation part of the workflow |
| B. Freeze it | | |
| C. Replace it | | |

**What shipped**

- **`docs/architecture/AUDIT_ID_INDEX.md`** — the canonical index of every ID in
  the source, with its meaning and every annotated location.
- **Four IDs backfilled.** `C1` (process-wide singleton), `M1` (drift wiring),
  `L2` (`health()` aggregation) and `L6` (bootstrap loop-safety) were referenced
  in the test suite's section comments but carried no annotation in `src/`. Their
  meanings were recoverable from the tests that assert them, so they are now
  annotated at the code they describe.
- **Ten IDs recorded as unrecoverable, not invented.** `FIX-07/09/10/12/13`, `M3`,
  `D-5/6/8/9` appear nowhere in source or tests, and the audit documents that
  defined them are not in this repository. Assigning them guessed meanings would
  make a fabricated trail indistinguishable from a real one, so §4 of the index
  names them and says so.
- **The workflow rule** is in `.claude/CLAUDE.md`: any change that introduces or
  closes an ID updates the index in the same commit.

> One correction the index records: `docs/context/01_SYSTEM_STATE.md:88` claims
> the full `FIX-01..FIX-14` range is "present and consistent". Nine of fourteen
> are annotated.
>
> One collision worth knowing: `H-1` in `dependency_injection.py` is the
> *eviction* finding, not the executor `H1`.

---

# What changed, in files

| Area | Files |
|---|---|
| Domain | `domain/validator.py`, `domain/schema_vocabulary.py`, `domain/__init__.py` |
| Ports | **`ports/lifecycle.py` (new)**, `ports/schema_storage.py`, `ports/event_bus.py`, `ports/validation_runner.py`, `ports/__init__.py` |
| Config | `config.py`, `security_limits.py` |
| Composition | `adapters/dependency_injection.py` |
| Public surface | `congine_core/__init__.py` |
| Packaging / CI | `pyproject.toml`, `.github/workflows/ci.yml` |
| Docs | `README.md`, `.claude/CLAUDE.md`, **`docs/architecture/AUDIT_ID_INDEX.md` (new)**, this file |
| Tests | **`test_readme_config_table.py` (new)**, `test_schema_vocabulary.py`, `test_sync_usecase.py`, `test_container_tenant_lru.py`, `conftest.py`, `test_validation_runner_port.py` |

**Config surface: 46 → 47 fields**, all documented, all wired, **zero dead
configurables** (`region` was the last one).

## Follow-ups this created

1. **Confirm the Q1 regional hostnames** — placeholders today.
2. **`ARCHITECTURE_CURRENT.md` is now partly stale.** It documents the
   pre-decision state: §12.4 (dead `region`), §13.6 (union-type crash), §16 debts
   D1/D2/D3/D6/D8/D9/D14/D16/D18/D21, §5.9 (port surface gap), and every line
   number in `config.py`, `dependency_injection.py` and `domain/validator.py`.
   Say the word and I'll re-run the affected passes.
3. **Phase C is unblocked but unbuilt** — see Q9.
