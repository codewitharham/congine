# Enterprise Hardening — Pre-Change Verification Report

**Produced:** 2026-08-17 · **Stage:** P0 Trust-Critical Hardening, Step 0
**Status:** verification complete — no production code mutated at time of writing.

---

## 1. Environment

| Field | Value |
|---|---|
| Source commit (HEAD) | `49a2f93294a1b594ec7eae8cbfedd439976d63e1` |
| Original branch | `ahmed-main-v2` |
| Worktree path | `C:/Users/USER/Documents/CONGINE_V2/congine-p0-hardening` |
| Worktree HEAD | `49a2f93` (detached) |
| Python | CPython 3.14.5 (MSC v.1944, 64-bit, win32) |
| Package | `congine-sdk 0.1.0` |
| Runner | `uv 0.11.19` |

### Worktree isolation — verified

The original working tree contains unrelated user changes and **must not be touched**. It was
fingerprinted before and after `git worktree add`:

```
git status --porcelain | sort | sha256sum
before: 1156abd187e4032596109f005e143eab9f5ea264c9a460f2371eba8c78f80bdc
after:  1156abd187e4032596109f005e143eab9f5ea264c9a460f2371eba8c78f80bdc   ← unchanged
stash entries: 0 (unchanged)
```

```
$ git worktree list
C:/Users/USER/Documents/CONGINE_V2/congine               49a2f93 [ahmed-main-v2]
C:/Users/USER/Documents/CONGINE_V2/congine-p0-hardening  49a2f93 (detached HEAD)
```

Nothing was stashed, restored, staged, deleted, cleaned, or committed in the original tree.

**Environment reproduction risk — resolved, no stop condition triggered.** The fresh worktree
contained only tracked files (no `.venv`, none of the untracked `docs/` material). `uv` provisioned
from the tracked `uv.lock` successfully — 46 packages in 5.72 s, including the native `google-re2`
wheel — and `import congine_core` succeeded.

---

## 2. Baseline (measured in the worktree)

```bash
uv run --package congine-sdk --extra langchain --extra stats --extra dev pytest libs/congine-sdk/tests -q
→ 350 passed, 1 skipped in 30.75s

uv run --package congine-sdk ruff format --check libs/congine-sdk
→ 80 files already formatted

uv run --package congine-sdk ruff check libs/congine-sdk
→ All checks passed!
```

Identical to the original tree's baseline (350 / 1, ruff clean), confirming environment parity.

The single skip is `tests/adversarial/test_remediations.py:193`
`test_symlinked_snapshot_is_refused` — "symlinks not permitted on this platform/user". It backs
guarantee G4's symlink-refusal layer and does not execute on Windows.

---

## 3. P0 findings — status at HEAD

Every row was confirmed by **executing** the defect, not by reading code.

| ID | Decision | Status | Evidence |
|---|---|---|---|
| **P0-01** | Runner health through the port | **STILL PRESENT** | `inspect.getsource(ServiceContainer.health)` contains `.in_flight` → `True`; contains `validation_executor.health()` → `False` |
| **P0-02** | Fail closed on unmeasurable size | **STILL PRESENT** | `inspect.getsource(_check_payload_size)` contains `size = 0` → `True` |
| **P0-03** | Dotted-path false safety | **STILL PRESENT** | contract `{"required":["user.email"],"properties":{"user.email":{"type":"string","pattern":"^.+@.+$"}}}` + payload `{"user":{"email":12345}}` → `status=pass`, `breaches=[]`; `find_unenforced_keywords` → `[]` |
| **P0-04** | Unknown type names | **STILL PRESENT** | `{"type":"str"}` + payload `{"a":12345}` → `status=pass`; `{"type":["string","mystery"]}` + `{"a":12345}` → `status=pass` |
| **P0-05** | Explicit evaluated/enforced signal | **STILL PRESENT** | `ValidationResult` public methods = `['is_pass']`; `hasattr(ValidationResult,'is_enforced')` → `False` |
| **P0-06** | Load shed vs timeout | **STILL PRESENT** | `hasattr(bounded_executor,'LoadShedError')` → `False`; both conditions collapse to `degraded_reason="timeout"` |
| **P0-07** | Strict configuration parsing | **STILL PRESENT** (all four) | `CONGINE_TELEMETRY_ENABLED='TRUE!'` → `False` silently · `CONGINE_CONTRACT_SOURCE='files'` → accepted, means HTTP · `CONGINE_LOCAL_CONTRACTS_DIR=''` → accepted, selects standalone · usecase `timeout_ms` default `15` vs config `100` |
| **P0-08** | Placeholder regional routing | **STILL PRESENT** | `_REGION_BASE_URLS = {'us': 'https://api.us.congine.dev', 'eu': ..., 'apac': ...}`; `CONGINE_REGION=eu` with no base URL → `base_url=https://api.eu.congine.dev` |

**All eight remain. None was found ALREADY FIXED, CHANGED SHAPE, or CANNOT VERIFY.**

---

## 4. Contradictions with the hardening package

Recorded before implementation, per execution protocol §0 and §3.

### C-1 · D15 is already fixed — do not modify

`libs/congine-sdk/README.md:85` reads:

> `drift_threshold` | `CONGINE_DRIFT_THRESHOLD` | `0.1` | KS **D-statistic** above which drift is
> flagged — not the p-value. Requires `[stats]`.

The package anticipated this might still be wrong. It is correct. No action.

### C-2 · The PII sanitizer cannot simply switch to RE2 (P1 item, blocked as written)

`pii_sanitize.py:14` uses `(['\"])(.*?)\1|(\b\d{4,}\b)` — a **backreference**. RE2 does not support
backreferences. Verified:

```
re2.compile(pattern) → Error b'invalid escape sequence: \\1'
```

Package 12/Q8 says "replace with RE2 **unless current code proves a technical incompatibility**".
It does. This requires a pattern redesign with equivalence tests, not an engine swap. **P1 scope —
not attempted in P0.**

### C-3 · §11.1 is unimplementable as literally written

`DeploymentMode` is `SINGLE_TENANT | MULTI_TENANT` — a *tenancy* concept, consumed only by
`get_default()` gating (`dependency_injection.py:116`) and the LangChain handler guard
(`langchain_handler.py:46`). Local-vs-remote is derived **from `base_url` itself** via
`is_local_base_url()`. So "remote deployment mode without explicit base URL → error" is circular:
omitting `base_url` yields the loopback default, which *is* local by definition. §11.1 forbids
inventing a mode.

**Founder-approved resolution:** `CONGINE_REGION` set **without** `CONGINE_BASE_URL` →
`CongineConfigurationError`. Region is the only existing field whose purpose is to declare a remote
deployment; this uses it without inventing anything. Local development (sets neither) is unaffected.

### C-4 · The schema cache is entirely version-blind — bounds the last-known-good rule

Verified:
- `ISchemaStorage.put(contract_id, schema, ttl_seconds)` — **no version parameter**
- `SyncContractsUseCase._prime_cache` reads only `contract.get("id")` and `contract.get("schema")` —
  any version field on the contract is ignored
- `ValidateContractUseCase.execute(payload, contract_id, contract_version)` — `contract_version` is
  passed only to `_finalize` → telemetry (`:213`, `:245`, `:257`). It is **never** matched against
  the cached schema.

Consequence: the achievable half of the amendment ("invalid update must never replace
last-known-good", make it explicit and observable) is implementable in P0. The other half ("if the
caller explicitly requires the rejected version → fail closed") is **not implementable today** and
is deferred to P1 with this finding recorded.

### C-5 · Unrelated repository state — untouched

The original tree carries 17 uncommitted markdown deletions, including
`libs/congine-sdk/SECURITY.md`, which `.claude/CLAUDE.md` still references
("see `SECURITY.md` for in/out-of-scope"). Unrelated to this task; **not touched, not resolved.**
Flagged for founder attention separately.

---

## 5. Decisions resolved before implementation

| Topic | Decision |
|---|---|
| Regional routing | Remove the placeholder mapping entirely; `region` becomes metadata; region-without-base-URL raises |
| Admission posture | Reject by default (`strict`), with a `warn` mode that relaxes **compatibility only, never correctness** |
| Bare-string property spec `{"a": "string"}` | **Reject** as `INVALID_STRUCTURE` — untested, absent from README, present only in a descriptive audit table, implemented as an incidental `isinstance(spec, dict) else spec` tolerance |
| `required="email"` (bare string) | **Reject** as `INVALID_STRUCTURE` — character-by-character iteration is accidental behaviour |
| `DegradedReason` members | Only values a concrete P0 path emits; **no `RESOURCE_LIMIT`** (nothing emits it, and the real resource path already emits `"resource_error"`) |
| `admit_contract` signature | Takes `enforced_keywords: frozenset[str]`, **not** a semantic-validator boolean |
| Scope / VCS | P0 only; **no commits**; all work in the isolated worktree |

---

## 6. Planned first code change

**Step 1 — P0-05 + P0-06: result semantics and typed degradation.**

Files:
- `libs/congine-sdk/src/congine_core/domain/models.py` — add `DegradedReason(str, Enum)` with the
  six verified members; add `ValidationResult.is_enforced()`.
- `libs/congine-sdk/src/congine_core/infrastructure/bounded_executor.py` — add
  `class LoadShedError(TimeoutError)`; raise it at the saturation site.
- `libs/congine-sdk/src/congine_core/usecases/validate_contract_usecase.py` — catch `LoadShedError`
  before `TimeoutError` in both sync and async paths; emit the typed reasons.
- `libs/congine-sdk/src/congine_core/__init__.py` — export `DegradedReason`.

This step is first because the reason vocabulary must exist before Steps 2 and 4 can emit precise
degraded states.

**Pre-existing wire values that must be preserved exactly** (verified at
`validate_contract_usecase.py:75,81,114,120,180`): `"timeout"`, `"resource_error"`,
`"internal_error"`.
