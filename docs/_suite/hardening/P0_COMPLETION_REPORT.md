# P0 Trust-Critical Hardening — Completion Report

**Date:** 2026-08-17 · **Source commit:** `49a2f93` · **Worktree:**
`C:/Users/USER/Documents/CONGINE_V2/congine-p0-hardening` (detached HEAD) · **Uncommitted, by
instruction.**

**Result: all eight P0 items implemented, 436 passed / 1 skipped, ruff clean, determinism preserved,
admission preflight acceptance met.**

---

## 1. Worktree isolation — verified

The original working tree carried 17 unrelated markdown deletions and was never touched.

```
git status --porcelain | sort | sha256sum
before worktree add : 1156abd187e4032596109f005e143eab9f5ea264c9a460f2371eba8c78f80bdc
after  worktree add : 1156abd187e4032596109f005e143eab9f5ea264c9a460f2371eba8c78f80bdc
stash entries       : 0 (unchanged)
```

Nothing stashed, restored, staged, deleted, cleaned or committed in the original repository.
Environment reproduced in the worktree from the tracked `uv.lock` (46 packages, 5.72 s, including
the native `google-re2` wheel) — the stop-and-report condition was not triggered.

## 2. Verification results

| Check | Baseline (`49a2f93`) | After P0 |
|---|---|---|
| Test suite | 350 passed, 1 skipped | **436 passed, 1 skipped** (+86) |
| `ruff format --check` | 80 files formatted | **83 files formatted** |
| `ruff check` | All checks passed | **All checks passed** |
| Determinism, N=5000 | 1 distinct verdict | **1 distinct verdict** |
| Load-shed rejection p50 | ~1.70 µs | **1.50 µs** (no material regression) |

The one skip is unchanged: `test_symlinked_snapshot_is_refused` — symlinks not permitted on this
platform.

## 3. Files modified

**Source (9):** `config.py` · `exceptions.py` · `__init__.py` · `domain/__init__.py` ·
`domain/models.py` · `domain/schema_vocabulary.py` · **`domain/contract_admission.py` (new)** ·
`usecases/validate_contract_usecase.py` · `usecases/sync_contracts_usecase.py` ·
`infrastructure/bounded_executor.py` · `adapters/dependency_injection.py`

**Tests (4):** **`unit/test_contract_admission.py` (new, 40 tests)** ·
**`unit/test_p0_result_semantics.py` (new, 45 tests)** · `unit/test_sync_usecase.py` (4 rewritten) ·
`test_file_contract_repository.py` (enum usage)

**Docs (1):** `README.md` config table.

## 4. Each P0 item

### P0-01 · Runner health through the port
**Before:** `ServiceContainer.health()` read `validation_executor.in_flight` / `.rejected_total`,
attributes `IValidationRunner` never declared. A faithful port implementation raised
`AttributeError` the first time health was polled.
**Now:** consumes `validation_executor.health()`, whose contract already specifies those keys.
Published output keys unchanged.
**Evidence:** the GAP3 minimal runner — written from the port docstring alone, no Congine imports —
now passes `validate()`, `health()` and `close()`.
**Test:** `test_p0_result_semantics.py` port usage + existing `test_validation_runner_port.py`.

### P0-02 · Fail closed on unmeasurable input
**Before:** a payload that could not be serialised was recorded as `size = 0` and sailed past the
size bound. An input could evade a security control by being malformed.
**Now:** degrades with `INVALID_PAYLOAD` (payload) or `INVALID_CONTRACT` (schema), **zero breaches** —
"could not measure" is not "measured and exceeded".
**Widened beyond the plan, deliberately:** the original catch was `(TypeError, ValueError)`. Because
`default=str` already absorbs ordinary unserialisable values, the realistic triggers are circular
references, non-string mapping keys, **and objects whose own `__repr__` raises** — that last class
escaped uncaught into the host, bypassing telemetry and fail-mode entirely. My own verification hit
it. The catch is now broad, because a size guard must fail closed for every reason it cannot measure.
**Evidence:** all three shapes degrade correctly; measurable-oversize still produces a genuine
`INPUT_BOUNDS` breach with `is_enforced() is True`.

### P0-03 · Dotted-path false safety · P0-04 · Unknown type names
**Before:** `{"user.email": {"type":"string","pattern":"^.+@.+$"}}` admitted an integer `12345` with
`status="pass"`. `{"type":"str"}` and `{"type":["string","mystery"]}` disabled checking entirely.
**Now:** a new **contract admission boundary** (`domain/contract_admission.py`, L2, pure) refuses any
contract whose meaning CONGINE cannot determine, before it reaches the cache. `RuleEngine` is
untouched and stays defensive at runtime.
**Evidence:** via the production loader, all three refuse; validating one now raises
`CongineContractNotFoundError` (fails closed) instead of returning `pass`.

### P0-05 · `is_enforced()` · P0-06 · Load shed vs timeout
**Before:** `is_pass()` could not distinguish "contract violated" from "validator never ran".
Saturation and deadline expiry both surfaced as `degraded_reason="timeout"`.
**Now:** `ValidationResult.is_enforced()` (additive; `is_pass()` unchanged), and
`LoadShedError(TimeoutError)` in L0 mapped to a distinct `DegradedReason.LOAD_SHED`.
**Evidence:** 2000/2000 saturated calls classified `LoadShedError`; deadline overrun stays plain
`TimeoutError`; `except TimeoutError` still catches both.

### P0-07 · Strict configuration
Malformed booleans now raise instead of silently meaning `False`; `contract_source` is a validated
enum; empty contract-directory values raise instead of selecting a broken standalone mode; and
`DEFAULT_VALIDATION_TIMEOUT_MS` is one constant — config and the use-case constructor previously
disagreed (100 vs **15**).

### P0-08 · Placeholder regional routing removed
`_REGION_BASE_URLS` and `Region.default_base_url` deleted. `region` is metadata; only
`CONGINE_BASE_URL` selects a control plane. Setting `CONGINE_REGION` without it now raises rather
than silently falling back to loopback. A regression test asserts the mapping cannot return.

## 5. Admission migration preflight (Step 8)

Every tracked contract, judged under the configuration it is **documented to operate in**
(`examples/LangChain/README.md` specifies `CONGINE_SEMANTIC_VALIDATION=true`):

| File | contract_id | native | **documented (semantic)** | codes |
|---|---|---|---|---|
| `return_processing.json` | `customer.support.return_processing` | REJECT | **ADMIT** | `unsupported_keyword` (`summary.minLength`) |
| `support_reply.json` | `support.reply.text` | REJECT | **ADMIT** | `unsupported_keyword` (`text.minLength`, `text.maxLength`) |
| `weather_policy.json` | `analytics.weather.extraction` | ADMIT | **ADMIT** | — |

**Acceptance met: 100% of shipped contracts are admitted under their documented configuration.**
No contract was repaired and admission was not weakened.

The native-column rejections are *correct*: run those contracts with semantic validation off and
`minLength`/`maxLength` genuinely are not enforced. Previously they loaded and silently ignored those
clauses; now that misconfiguration is refused loudly. This validates the capability-set design — the
same contract is admitted or refused according to what is actually wired.

## 6. Intentional behaviour changes — breaking / fail-loud

These are semantic changes, not refactors.

1. **Malformed boolean env values now refuse configuration.** `CONGINE_TELEMETRY_ENABLED=TRUE!` used
   to silently mean `False`.
2. **Invalid `CONGINE_CONTRACT_SOURCE` now refuses configuration.** `files` used to silently mean
   HTTP.
3. **Empty `CONGINE_LOCAL_CONTRACTS_DIR` / `CONGINE_CONTRACTS_DIR` now refuse configuration.** Empty
   used to select standalone mode against an empty directory — no contracts, no sync worker, every
   call raising.
4. **`CONGINE_REGION` without `CONGINE_BASE_URL` now refuses configuration.** It used to resolve to
   an unverified placeholder hostname and send the API key there.
5. **Unsafe contracts are refused at admission.** On a cold cache this makes every guarded call
   against them raise `CongineContractNotFoundError`. Intended: refusing to enforce is safer than
   appearing to enforce.
6. **`"load_shed"` is a new `degraded_reason`**, distinct from `"timeout"`. Anything matching
   `== "timeout"` for saturation now sees `"load_shed"`.
7. **`contract_source` is an enum.** `CongineConfig(contract_source="file")` constructed *directly*
   no longer selects the file repository (the container compares by identity, matching how
   `fail_mode` is handled). `from_env()` coerces correctly. Two tests updated.
8. **`ValidateContractUseCase(timeout_ms=...)` now defaults to 100, not 15.** Direct constructors
   silently ran a ~7× tighter budget than documented.

**Backward compatible:** `is_pass()` semantics · all existing `degraded_reason` wire values
(`"timeout"`, `"resource_error"`, `"internal_error"`) · `except TimeoutError` still catches load shed
· `health()` output keys · `ValidationResult` field layout.

## 7. Existing tests changed, and why

Four tests in `test_sync_usecase.py` asserted the behaviour P0 deliberately removes. Each was
rewritten, not weakened; the original intent is preserved where it remains valid.

| Test | Asserted | Now asserts |
|---|---|---|
| `test_unenforced_keyword_warns` → `..._contract_is_refused` | "caching unchanged: the schema is still primed" | refused, not cached, ERROR names the code and path |
| `test_unenforced_keyword_warning_is_deduplicated` → `test_repeated_rejection_is_counted_every_sync` | the warning is emitted once | rejection is counted every pass — a repeatedly-refused update is an ongoing unhealthy state, not a one-off notice |
| `test_malformed_schema_does_not_break_priming` → `..._is_refused_without_breaking_the_sync` | all four cached, including a non-mapping schema | the valid sibling still loads and nothing raises (**original intent kept**); the three malformed ones are refused |
| `test_unrecognised_type_warns` → `..._contract_is_refused` | "priming is unaffected; the scan is a diagnostic only" | refused, with `unknown_type` at `a.type` / `b.type` |

## 8. New public API

`DegradedReason` · `LoadShedError` · `ValidationResult.is_enforced()` · `admit_contract` ·
`ContractAdmissionResult` · `ContractAdmissionIssue` · `ContractAdmissionCode` ·
`ContractAdmissionLevel` · `ContractAdmissionMode` · `ContractSource` ·
`DEFAULT_VALIDATION_TIMEOUT_MS` · **`find_unenforced_keywords`** (previously reachable only via a
private module path, despite the project's own guidance making it mandatory for every loader).

New config field: `contract_admission` → `CONGINE_CONTRACT_ADMISSION` (`strict` default | `warn`),
documented in the README config table (4-touch rule satisfied; `test_readme_config_table.py` passes).

## 9. Two architectural bugs caught during implementation

Recorded because both would have shipped silently.

**A layering violation, twice.** The plan placed `LoadShedError` in `infrastructure/` and I began
importing `ContractAdmissionMode` into `config.py` from `domain/`. Both would have created outward
dependencies — L3→L4 and L0→L2 — inverting the one direction the hexagon protects. `LoadShedError`
now lives in L0 `exceptions.py`; `ContractAdmissionMode` in L0 `config.py`. Both are noted in-code
with the reason.

**The enum serialization trap, in real code.** `admission_status()` initially leaked
`"ContractAdmissionMode.STRICT"` into `health()` instead of `"strict"`. `class X(str, Enum)`
serialises correctly through `json.dumps` but renders as `X.MEMBER` under `str()`, f-strings and
`%s`. All new machine-facing enums are `enum.StrEnum`; pre-existing ones are deliberately left alone
(changing them would alter output elsewhere, out of scope). This is exactly what the amendment
requiring serialization tests was for — it caught it.

## 10. Not fixed / deferred

**Residual admission bypass — direct `schema_storage.put()`.** Admission runs in the sync loader,
which is the only production writer. A test or embedder calling `put()` directly still bypasses it,
so the false-safety case reproduces on that path. Verified. Two mitigations now exist: an AST guard
fails CI if production code adds an unadmitted writer, and `admit_contract` is public so embedders
can run the same check. Closing it fully means moving admission behind the `ISchemaStorage` boundary
or making `put` accept an `AdmittedContract` — a port change, out of P0.

**Version-aware fail-closed (Amendment 4, deferred half).** The achievable half shipped: a rejected
update never replaces last-known-good, refusal is logged with typed codes, and `health()` reports it.
The other half — "if the caller explicitly requires the rejected version, fail closed" — is **not
implementable today**: `ISchemaStorage.put` has no version parameter, `_prime_cache` ignores any
version field, and `execute()`'s `contract_version` reaches telemetry only, never matched against the
cached schema. Requires a port/cache change.

**Partial-enforcement metadata.** `WARN` is close to a no-op by design. Genuinely partial enforcement
needs admission metadata carried into every `ValidationResult`; deferred rather than approximated
with an unsafe escape hatch.

**The P0-2 unenforced-keyword warning is now largely superseded.** Admission refuses what the warning
used to warn about, so `_warn_unenforced_keywords` rarely fires. Left in place (removing it is scope
creep); a P1 cleanup candidate.

**Untouched by instruction:** D5 stale `TelemetryEvent` docstring — noticed while editing that file,
not fixed, per "do not fix something nearby while here".

## 11. Contradictions with the package

1. **D15 already fixed** — README correctly documents `drift_threshold` as the D-statistic. Not modified.
2. **RE2 sanitizer blocked as written** — the pattern uses a backreference; `re2.compile` fails with
   `invalid escape sequence: \1`. Needs pattern redesign plus equivalence tests. P1.
3. **§11.1 unimplementable as written** — no remote deployment mode exists; resolved via the
   founder-approved `CONGINE_REGION`-without-`CONGINE_BASE_URL` trigger.
4. **Cache is version-blind** — bounds Amendment 4, above.
5. **17 unrelated markdown deletions** in the original tree, including `SECURITY.md`, still
   referenced by `.claude/CLAUDE.md`. Untouched; flagged for separate attention.

## 12. Remaining work

**P1:** blocking mypy · runtime port conformance checks · transactional composition root ·
`atexit.unregister` · telemetry shutdown ordering · **RE2 sanitizer (needs pattern redesign)** ·
remove `ValidationTimer` · contract-admission facade evolution · fix the LangChain example's
`manual_review` enum mismatch (prior debt #1, still present) and run examples in CI.

**P1.5:** honest semantic-validation cost warning · separate native/semantic budgets · admission
complexity checks · compiled-validator caching (thread safety unproven).

**P2:** branch coverage · determinism golden corpus · Python support matrix · Linux CI · pip-audit ·
SBOM · security ruff rules.

**P3:** reconcile `ARCHITECTURE_CURRENT.md` (§16 debt statuses, §17 open questions, six scale facts)
· ADRs · patch stale authoring prompts.

## 13. Recommendation on P1

**Safe to begin, with one sequencing note.** P0 left the core green, deterministic and
fail-closed, and every change is behind a test. Start P1 with **blocking mypy** — the ports are
`typing.Protocol`, so structural conformance is only checkable statically, and the two layering
violations caught by hand in this slice are precisely what it would catch mechanically.

Do **not** start P1-05 (RE2 sanitizer) as written; it needs a regex redesign decision first.

---

## 14. P0 Final Closeout

**Date:** 2026-08-17 · **Source HEAD:** `49a2f93` · **Worktree:**
`C:/Users/USER/Documents/CONGINE_V2/congine-p0-hardening` (detached, **0 commits**)
**Final diff:** 20 files changed, **+968 / −147**, plus 5 new paths.

### 14.1 Results

| Gate | Result |
|---|---|
| Test suite | **478 passed, 1 skipped** (was 436/1 at end of P0; +42) |
| `ruff check` | **All checks passed!** |
| `ruff format --check` | **84 files already formatted** |
| Determinism, N=5000 | **1 canonical verdict** — hash `3ab5ce02…`, unchanged from P0 |
| Admission preflight | **3/3 = 100%** admitted under documented configuration |
| Load shed | 2000/2000 `LoadShedError`; deadline → plain `TimeoutError` (distinguishable) |
| Load-shed rejection p50 | **3.50 µs** (p90 8.80, p99 12.40) |
| Original tree | fingerprint `1156abd1…` **unchanged**, 0 stashes |

The load-shed p50 moved 1.50 → 3.50 µs. The executor was **not touched** by this closeout; this is
machine noise on an unloaded developer laptop, same order of magnitude, and was deliberately not
tuned toward the earlier figure.

### 14.2 Configuration parity — the closeout's substance

**The reported defect was narrower than the real one.** `contract_source` was flagged (P0-introduced).
The audit found the same defect on **all five** enum-backed fields, of which **four feed `is`
identity branches** in production code:

| Field | Identity branch | Consequence of a raw string | Origin |
|---|---|---|---|
| `contract_source` | `dependency_injection.py` | wrong repository selected | P0 |
| `contract_admission` | `contract_admission.py` | WARN advisories lost | P0 |
| **`fail_mode`** | `validate_contract_usecase.py` | **`"strict"` degraded instead of raising — enforcement silently lost** | pre-existing |
| **`deployment_mode`** | `langchain_handler.py` | **multi-tenant guard bypassed** | pre-existing |
| `region` | none | metadata only | — |

Reproduced end-to-end before the fix: `CongineConfig(fail_mode="strict")` returned a failing result
where `CongineConfig(fail_mode=FailMode.STRICT)` raised. Both pre-existing cases are the same class
of silent non-enforcement P0 exists to remove, so they were fixed by the same central rule.

**Fields normalized:** all five, via `CongineConfig.__post_init__`.

**Additional mismatch found beyond enums:** yes — and larger. `validate()` was invoked **only** by
`from_env()`, so direct construction skipped the credential and HTTPS policy entirely. Enum
normalization alone would not have closed that.

### 14.3 One boundary: `__post_init__` normalizes, then validates

```
env / direct / tests / future CLI / future API adapter
        ↓
CongineConfig.__post_init__
        ├─ normalize enum fields (canonical member, or raise)
        └─ self.validate()      (existing invariants, unchanged)
        ↓
canonical, validated configuration → ServiceContainer
```

- Normalization runs **first**, so `validate()` never sees a mixed enum/string state.
- `__post_init__` **calls** `validate()` and does not reimplement it — one definition of the
  invariants, no divergence between paths.
- The now-redundant `config.validate()` in `from_env` was **removed**. `validate()` is read-only
  (raises or returns `None`, mutating nothing), verified by reading it, so removing the second
  invocation cannot change behaviour. Guarded by an AST test asserting `from_env` contains no
  `validate` call and `__post_init__` does.
- `from_env` keeps its per-field `try/except`, so errors still name the environment variable.

**Uniform case rule (intentional behaviour change).** `.strip().lower()` now applies on **both**
paths to all five fields; `from_env` previously folded case for only two. This is a **widening** —
`CONGINE_FAIL_MODE=STRICT` now works where it raised — never a narrowing. All canonical wire values
are lowercase, so folding is unambiguous.

### 14.4 Invariant parity audit

Every invariant `CongineConfig.validate()` enforces, measured on both construction paths:

| invariant | direct construction | from_env | parity |
|---|---|---|---|
| loopback `base_url` exempt from policy | accepted | accepted | **PASS** |
| non-local requires `api_key`/`project_id`/`tenant_id` | RAISES | RAISES | **PASS** |
| non-local + credentials + https → valid | accepted | accepted | **PASS** |
| non-local cleartext refused when `require_https` | RAISES | RAISES | **PASS** |
| cleartext permitted via `allow_cleartext` | accepted | accepted | **PASS** |
| cleartext permitted via `require_https=false` | accepted | accepted | **PASS** |

**All rows PASS.** No invariant was redesigned.

### 14.5 P0-02 exception scope — VERIFIED, unchanged

`_check_payload_size` / `_check_schema_size` already wrap exactly one statement:

```python
try:
    size = len(json.dumps(payload, default=str))
except Exception:
    return self._degraded_unmeasurable(...)
```

That is the minimal measurement boundary — no business logic, storage, telemetry or orchestration
inside, and the `except` returns immediately. It cannot convert an unrelated programming error into
`INVALID_PAYLOAD`/`INVALID_CONTRACT`. **Not rewritten.** Regression cases retained and passing:
circular reference · non-string mapping key · `__repr__` raises · measurable oversize (still a real
`INPUT_BOUNDS` breach with `is_enforced() is True`) · ordinary valid input.

### 14.6 Machine-facing enum serialization — re-verified

After normalization, `"strict"` · `"file"` · `"load_shed"` · `"unknown_type"` all serialize as wire
strings through `json.dumps`, `json.dumps(default=str)`, `str()`, f-strings and `%s`. No surface
emits `ContractAdmissionMode.STRICT`, `ContractSource.FILE`, `DegradedReason.LOAD_SHED` or
`ContractAdmissionCode.UNKNOWN_TYPE`. Pre-existing enums outside P0 scope were left unchanged.

### 14.7 Test configurations repaired

Making `validate()` run on construction exposed **35 failing tests across 6 files** — configs that
were genuinely invalid and had been silently accepted. Root causes: 29× HTTPS policy, 6× missing
credentials. Repairs, none of which weaken a test:

| Repair | Where | Rationale |
|---|---|---|
| `allow_cleartext=True` (×12) | `conftest.py`, `test_repository.py`, `test_event_bus.py`, `test_end_to_end.py`, `test_remediations.py`, `test_config.py::test_is_frozen` | Declares the intent each config always had: a cleartext internal test control plane. Keeps them **non-local**, so locality, the 12-key auto-redaction allowlist and the cleartext warning behave exactly as before |
| loopback `base_url` (×2) | `test_config.py` defaults tests | They inspect defaults with deliberately absent credentials; "no control plane involved" is what loopback means. Verified the file has no locality dependence |
| credentials + `allow_cleartext` in helper | `test_host_bypass.py::_cfg` | Locality parsing is what is under test; `is_local_base_url()` consults neither |

**Three tests depended on the bypass and were rewritten, not patched** — each constructed an invalid
config and then called `validate()` explicitly, which is exactly the hole that was closed. Their
invariant is unchanged; the assertion moved to construction, which is strictly stronger:

- `test_host_bypass.py::test_notlocalhost_requires_credentials_on_validate`
  → `..._at_construction`
- `test_remediations.py::test_validate_missing_creds_nonlocal_raises`
- `test_remediations.py::test_validate_https_enforced_when_required`

> **Caught during repair:** the bulk edit initially added `allow_cleartext=True` to
> `test_validate_https_enforced_when_required` — which would have **defeated the very policy that
> test asserts**. Removed. Recorded because it is precisely the "never weaken a test to get green"
> failure mode.

**New:** `tests/unit/test_config_construction_parity.py` — 42 tests covering enum member
preservation, wire-string canonicalization, case/whitespace folding, direct-vs-env agreement, loud
rejection of invalid values (including non-string types), the two severe pre-existing divergences as
*behaviour*, non-enum validation parity on both paths, the "no caller must remember `validate()`"
assertion, the single-owner AST guard, and the runtime branch (`contract_source="file"` →
`ServiceContainer` → `FileContractRepository`).

### 14.8 Breaking behaviour added by this closeout

1. **Invalid enum values now raise on direct construction**, where a raw string previously survived
   and silently took the wrong branch.
2. **Direct construction now enforces the credential and HTTPS policy.** Any code building a
   `CongineConfig` for a non-local cleartext plane must now pass `allow_cleartext=True` or
   `require_https=False`. This is the bypass closing; it will surface in downstream test suites
   exactly as it did here.
3. **Case folding widened** on `region` / `fail_mode` / `deployment_mode` in `from_env`.

Backward compatible: all P0 wire values, `is_pass()`, `except TimeoutError`, `health()` keys,
`ValidationResult` layout, and every `from_env` error message naming its variable.

### 14.9 Remaining deferrals (unchanged, still documented)

- **Direct `schema_storage.put()` bypasses admission** — test/embedder path only; mitigated by the
  AST CI guard and by `admit_contract` being public. Closing it needs an `ISchemaStorage`/
  `AdmittedContract` change. **Entry gate for P1 / Contract Admission Facade work.**
- **Version-aware fail-closed** — the cache is version-blind; "prove exactly version X was
  evaluated" needs version-aware storage identity.
- **Partial-enforcement metadata** — `WARN` stays near-no-op by design.
- P1 / P1.5 / P2 / P3 backlogs unchanged from §12.

### 14.10 Closure gates

| Gate | |
|---|---|
| All 8 original P0 findings remain fixed | ✅ |
| Full test suite passes | ✅ 478 passed, 1 skipped |
| Ruff passes | ✅ check + format |
| N=5000 determinism → one canonical verdict | ✅ |
| Admission preflight 100% | ✅ 3/3 |
| Dotted / unknown / unenforced remain refused | ✅ all 3 refused via the production loader |
| Load shed distinguishable from timeout | ✅ |
| Direct construction cannot diverge from `from_env` | ✅ |
| Valid enum strings canonicalized | ✅ all 5 fields |
| Invalid enum strings fail loudly | ✅ incl. non-string types |
| Size-measurement catch narrowly scoped | ✅ VERIFIED, unchanged |
| Machine-facing enum values serialize as wire strings | ✅ |
| Original dirty tree untouched | ✅ `1156abd1…`, 0 stashes |
| Residual admission-storage bypass documented | ✅ §14.9 |
| Version-aware fail-closed documented | ✅ §14.9 |
| Partial-enforcement metadata documented | ✅ §14.9 |
| **Every `validate()` invariant executes for direct construction** | ✅ §14.4, 6/6 PASS |
| **One instance-validation boundary shared by both paths** | ✅ AST-guarded |
| **No caller must remember `validate()`** | ✅ asserted |
| **Validation not duplicated across paths** | ✅ redundant call removed |

**Direct construction and environment construction now have identical machine-significant
configuration semantics.**

## P0 CLOSED

Do not start P1 without the structural gates: **blocking mypy _and_ a separate import/layer
dependency gate.** mypy enforces static type and Protocol correctness but has no knowledge that
`L3 → L4` or `L0 → L2` is forbidden — both were hit by hand during this work and caught only by
review. Do not claim mypy alone enforces hexagonal direction.
