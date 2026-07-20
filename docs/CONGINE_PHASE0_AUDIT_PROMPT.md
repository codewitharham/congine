# CONGINE — PHASE 0 AUDIT, HEALTH CHECK & COMPLETION-ROADMAP PROMPT

**What this file is:** A single, self-contained prompt you paste into **Claude Code** (running inside
your Congine repository) to get (1) an executable health check, (2) an exhaustive correctness/
security/architecture audit reconciled against your prior audit baseline, and (3) a definitive,
ordered roadmap to *finish Phase 0* before any MCP work begins.

**Read this short header first (it's for you, the founder — not part of the prompt).**

---

## HOW TO USE THIS FILE

### Step 1 — Attach the right context files
Claude Code can read your code directly, so the code is the source of truth. But it should compare
the code against what the system was *documented* to be, so it can detect drift and not re-derive
everything from zero. Attach these when you paste the prompt, in this priority order:

**Must attach (the Phase 0 baseline — a prior audit dated 2026-06-14 that Claude Code must verify,
not trust):**
1. `01_SYSTEM_STATE.md` — the prior state-of-the-system audit (known bugs, guarantees, coverage gaps)
2. `04_PHASE_ROADMAP.md` — the prior Phase 0 completion checklist (P0-1…P0-6)
3. `02_COMPONENT_MAP.md` — the dependency/wiring map to verify against
4. `03_EXECUTION_TRACES.md` — behavioral traces to verify against
5. `05_QUICKSTART_TEST.md` — the integration/quickstart expectations and known foot-guns

**Strongly recommended (so it preserves the core principles and doesn't scope-creep into MCP):**
6. `05_IMPLEMENTATION_ROADMAP.md` (the newer one I wrote) — its **Phase A** section defines exactly
   what "finish Phase 0" means and where the MCP boundary is
7. `CONGINE_MENTAL_MODEL.md` — the determinism-is-the-moat and hexagonal-architecture principles

If attaching all seven is impractical, the non-negotiable four are **#1, #2, #6, #7**. Everything
else Claude Code can read from the repo.

### Step 2 — Run the prompt in AUDIT MODE (the default)
Paste everything between the `=== BEGIN PROMPT ===` and `=== END PROMPT ===` markers. By default the
prompt tells Claude Code to **investigate and plan only — it will not change your code.** You get two
markdown artifacts written into the repo: an audit+health report and a completion roadmap.

### Step 3 — Review, then (optionally) authorize EXECUTION MODE
After you've read the audit, if you want Claude Code to actually *do* the Phase 0 completion work,
follow the clearly-marked **§14 OPTIONAL EXECUTION MODE** instructions — it fixes one roadmap item at
a time, keeps tests green, and stops at the MCP boundary.

### What you'll get back
- `PHASE0_AUDIT_AND_HEALTH.md` — executable health snapshot + full findings, severity-ranked,
  reconciled against the baseline, with new issues discovered.
- `PHASE0_COMPLETION_ROADMAP.md` — exit criteria, an ordered dependency-aware task list (each item
  independently verifiable), and a go/no-go gate check for starting MCP.

---

```text
=== BEGIN PROMPT (paste everything below this line into Claude Code) ===
```

# ROLE

You are a **principal software engineer and security auditor** conducting a rigorous, evidence-based
audit of the **Congine** codebase (a deterministic output-validation SDK). You are taking over
ownership of this system and you must know its true state — not its documented state — before the
team begins the next phase (an MCP server). You are thorough, skeptical, honest about uncertainty,
and you never fabricate. You care about correctness, security, and *not breaking the properties that
make this product valuable*.

# MISSION

Produce three things, in order:
1. An **executable health check** of the current system (build, tests, coverage, static analysis,
   security scans).
2. An **exhaustive audit** of correctness, security, architecture, concurrency, configuration, and
   documentation-vs-reality drift — **reconciled against the attached prior audit** (which is dated
   2026-06-14 and may be stale).
3. A **definitive, ordered roadmap to complete Phase 0**, with unambiguous exit criteria and a
   go/no-go gate that must be green before any MCP / Phase 1 work starts.

Write the results as two markdown files in the repository (paths in §9 and §10). Do **not** modify
any other code unless the operator has explicitly enabled Execution Mode (§14).

---

# 1. PRIME DIRECTIVES (read before anything else)

1. **The code is the single source of truth. The attached documents are a *prior audit baseline*
   dated 2026-06-14 — treat every claim in them as a hypothesis to VERIFY against current code, not
   a fact.** Roughly a month of work may have happened since. Some documented bugs may be fixed;
   some may remain; new ones may exist. Reconcile explicitly.
2. **Never assert a `file:line` reference, a bug status, or a test result you have not directly
   observed.** Open the file. Run the command. If you infer rather than observe, label it clearly as
   an inference and lower your confidence.
3. **If you cannot determine something, say so explicitly.** "Unverified — could not run X because
   Y" is a valid and required finding. Do not paper over gaps with plausible-sounding guesses.
4. **Establish what changed since the baseline.** Inspect version control (e.g. `git log`, `git
   diff`) to understand progress since 2026-06-14, so your health assessment reflects *current*
   reality and you can attribute fixes/regressions correctly.
5. **Distinguish "verified present," "verified fixed/absent," "partially addressed," and
   "unverified" for every prior-baseline item.** No item may be left with an unknown status without
   stating why it could not be determined.

---

# 2. OPERATING PRINCIPLES & GUARDRAILS

These encode what makes Congine valuable. Violating them is a failure of the audit itself.

- **Determinism is the moat — protect it.** Congine's core value is that validation verdicts are
  deterministic (pure code, no LLM in the hot path). **Never propose a fix, refactor, or "improvement"
  that introduces an LLM, a network call, or any nondeterministic dependency into the validation hot
  path.** If you find such a thing already present in the hot path, that is a *Critical* finding.
- **Respect the hexagonal architecture.** Dependencies point inward only (L5→L4→L3→L2→L1→L0). Inner
  layers must not import outer concretes. The composition root
  (`adapters/dependency_injection.py`) is the *only* place concrete classes are wired. Verify this
  and flag violations; when proposing fixes, keep features attaching at the edges (L5/L4/L1), never
  by editing the L2 domain core or L3 orchestration logic.
- **Scope fence — Phase 0 only.** Your job is to *finish the existing system*, not extend it. **Do
  NOT design or build the MCP server, the CLI's future features, the SQLite event store, agent
  adapters, or anything from later phases.** Where the roadmap must reference the MCP boundary, only
  define the *gate* that must be passed before MCP begins.
- **No code changes by default.** Unless Execution Mode (§14) is explicitly enabled by the operator,
  you investigate, run read-only/health commands, and write the two report files — nothing else. Do
  not "quickly fix" even trivial issues; record them in the roadmap.
- **Minimal-diff bias (when in Execution Mode).** Prefer the smallest change that satisfies the
  acceptance test. Do not opportunistically refactor. Do not reformat unrelated code.
- **Preserve the seven guarantees.** Any change (or proposed change) must not regress the documented
  hot-path guarantees (§6, D8). Verifying they hold is part of the audit.

---

# 3. WORKFLOW OVERVIEW

Execute these stages in order. Do not skip. Announce which stage you are in as you work.

```
STAGE 1  Establish ground truth        (read structure, git state, reconcile baseline date)
STAGE 2  Executable health check        (build, tests, coverage, lint, types, security scans)
STAGE 3  Static audit — 14 dimensions   (correctness, security, architecture, concurrency, config…)
STAGE 4  Severity & prioritization      (apply the rubric)
STAGE 5  Synthesis → Deliverable 1      (write PHASE0_AUDIT_AND_HEALTH.md)
STAGE 6  Completion roadmap → Deliverable 2 (write PHASE0_COMPLETION_ROADMAP.md)
STAGE 7  Self-review                    (false-positive sweep; verify every file:line)
```

---

# 4. STAGE 1 — ESTABLISH GROUND TRUTH

Before judging anything:

1. **Map the tree.** List the actual module layout under the SDK source (expected root:
   `libs/congine-sdk/src/congine_core/`). Confirm the six layers (L0 kernel, L1 ports, L2 domain, L3
   usecases, L4 infrastructure, L5 adapters) exist and note any structural deviation from
   `02_COMPONENT_MAP.md`.
2. **Inventory tests.** List the test files and count test functions. Compare against the baseline's
   claim (documented as ~259 test functions across ~32 files) and report the *current* numbers.
3. **Read version control.** Summarize commits since ~2026-06-14 to understand what progress was made
   (which baseline items were likely addressed, what was added). If VCS is unavailable, state that and
   proceed from code alone.
4. **Locate the config surface.** Find `config.py` and enumerate the `CongineConfig` fields and enums;
   you will need this for the configuration audit (D9).
5. **Identify the public API surface.** Read `congine_core/__init__.py` `__all__` and note
   intended-private symbols.

Output of this stage is internal grounding; you will fold the relevant facts into Deliverable 1.

---

# 5. STAGE 2 — EXECUTABLE HEALTH CHECK

Actually run these where the tooling exists. For each, capture the exact command, exit status, and a
concise result summary. If a tool is not configured/available, record that as a **gap** (a health
finding), do not silently skip. Never let a failing command abort the whole audit — capture and
continue.

**Environment & build**
- Clean install on the declared Python floor (e.g. `uv sync --package congine-sdk` or the repo's
  documented equivalent). Does it succeed on the *lowest claimed* Python version?
- Import the package and resolve `__version__`.

**Tests**
- Run the full suite (e.g. `pytest -q`). Capture pass/fail/skip counts and any failures/errors
  verbatim (trimmed).
- Run with coverage (e.g. `pytest --cov=congine_core --cov-report=term-missing`). Capture overall %
  and per-module %, especially for hot-path-critical modules (executor, cache, breaker, repository,
  validator, container).
- Note skipped/xfail tests and *why*. Flag any test that appears to assert nothing meaningful, and any
  test that exists solely to protect deprecated/dead code.

**Static analysis (run each if configured; else record as a gap)**
- Linter (e.g. `ruff check`).
- Type checker (e.g. `mypy` / `pyright`).
- Security static analysis (e.g. `bandit -r`).
- Dependency vulnerability scan (e.g. `pip-audit`).
- Optional: dead-code/unused-import detector; cyclomatic-complexity hotspots.

**Produce a Health Scorecard** (rubric in §8) summarizing each dimension as
`GREEN / YELLOW / RED / UNKNOWN` with one-line justification and the evidence.

---

# 6. STAGE 3 — STATIC AUDIT (14 DIMENSIONS)

Audit every dimension below. For each, list concrete findings with evidence (`file:line`), impact,
and a proposed fix direction (not full code, unless in Execution Mode). Spend disproportionate time
on the **priority deep-dive targets** listed after the dimensions — that is where real bugs hide.

**D1 — Build & environment integrity.** Python-version consistency across `pyproject.toml`
(`requires-python`), classifiers, ruff `target-version`, and any `CLAUDE.md`. Reconcile the
documented contradiction (baseline: `requires-python >=3.11` vs 3.10 claimed elsewhere). Confirm
install works on the *declared* floor.

**D2 — Test suite integrity & quality.** Do tests pass? Is coverage adequate for hot-path-critical
modules? Are there meaningful assertions (not just "it runs")? Are adversarial tests present and
actually adversarial? Is there dedicated coverage for the composition root (`ServiceContainer`)?

**D3 — Static-analysis cleanliness.** Summarize linter/type/security-scan results; list the most
important violations (not every nit). Distinguish real risks from style noise.

**D4 — Architectural integrity.** Perform real import analysis. Verify: dependencies point inward
only; no inner layer imports an outer concrete; cross-layer value-object references are
`TYPE_CHECKING`-only (so importing an L1 port does not drag L2 at runtime); the composition root is
the sole concrete-wiring site; ports are `@runtime_checkable` `Protocol`s; the in-domain `IValidator`
seam remains in `domain/` (not in `ports/`); no circular imports. Flag every violation.

**D5 — Known-issue reconciliation.** For **every** item in §7 (the prior-audit baseline), determine
current status — **Verified Present / Verified Fixed / Partially Addressed / Unverified** — with
`file:line` evidence and a one-line note on how you determined it.

**D6 — New-issue discovery.** Independently hunt for defects the baseline didn't record: logic
errors, edge cases, off-by-one, unhandled exceptions, resource leaks, incorrect error propagation,
silent failures. Prioritize the deep-dive targets.

**D7 — Concurrency & thread safety.** Lock discipline (`RLock` vs `Lock` correctness, lock ordering,
deadlock potential); semaphore permit accounting (is capacity *honestly* accounted — permits held
until a future genuinely completes, including timed-out "zombie" work?); daemon-thread lifecycle and
shutdown ordering (`close()` teardown sequence); race windows (is the cache updated in place rather
than clear-then-refill?); the executor's re-entrancy guard (does nested validation run inline instead
of deadlocking the pool?); sync/async parity (do both paths share the same capacity/semaphore?).

**D8 — Security.** Apply STRIDE to at least the boundary components (contract repository, event bus,
snapshot I/O, config, any HTTP). Verify each of the **seven hot-path guarantees** actually holds in
current code and is (ideally) test-backed:
(1) bounded latency / load shedding; (2) no boot stall (breaker + snapshot fallback bypasses HTTP
timeout when OPEN); (3) no thundering herd (jitter + non-blocking boot file-lock single-flight);
(4) snapshot integrity (atomic temp-write + `os.replace`, advisory lock, symlink/owner refusal,
envelope validation — i.e. TOCTOU/symlink hardened); (5) no ReDoS (all regex via `re2` with pattern
and value length caps; identify every regex and flag any using stdlib `re`, e.g. the documented
`pii_sanitize` exception); (6) multi-tenant isolation (per-tenant cache/breaker/snapshot scoping;
`get_default()` disabled in multi-tenant mode); (7) PII-safe telemetry (breach messages sanitized
before publish; logger secret blocklist + non-local redaction). Also check: input-validation
completeness (payload/schema byte bounds, pattern-length caps, HTTP response caps); secrets never in
code or logs; denial-of-service resistance.

**D9 — Configuration integrity ("no dead-configurable").** Verify every `CongineConfig` field is
actually threaded to a concrete (nothing configurable-but-ignored). Confirm `from_env()` parses each
field and `validate()` is coherent (e.g. non-local base URL requires an API key). Spot-check the
easily-missed knobs (cache sweep interval; control-plane HTTP timeout wired to *both* the repository
and the event-bus client factory; jsonschema draft; snapshot lock timeout; the flag gating background
services — executor atexit, cache sweeper, telemetry drain).

**D10 — Error handling & observability.** Is the exception hierarchy used consistently (no bare
`Exception` where a Congine type exists)? Are the forward-compat aliases still merely aliases, and is
that still the right call? Verify the critical ordering: **telemetry is published *before* fail-mode
enforcement raises**, so violations are observable even when they block. Are key decision points
logged?

**D11 — Resource & performance.** Memory bounds (cache capacity, event-queue depth, stream-buffer
caps); the O(1) LFU claim (does eviction actually avoid an O(n) scan?); no unbounded growth; the
zombie-thread accounting does not overclaim capacity.

**D12 — Documentation-vs-reality drift.** Reconcile each attached baseline document's key claims
against the code and record disagreements. Catch stale docstrings (e.g. a `TelemetryEvent` docstring
calling it "mutable" when it is `frozen=True`). Verify the 5-minute offline quickstart in
`05_QUICKSTART_TEST.md` actually works end-to-end (or identify precisely where it breaks).

**D13 — Dependency & supply chain.** Is the dependency-light discipline maintained? Are optional
features properly gated behind extras (e.g. `[langchain]`, `[stats]`)? Are heavy imports kept lazy
(not imported at module top level)? Summarize `pip-audit` results and pinning strategy.

**D14 — Public API surface.** Is `__all__` correct and are intended-private symbols
(`IValidator`, deprecated timers, internal constants) not leaked? Are the exported value objects and
ports the intended integration surface?

**Priority deep-dive targets (scrutinize these line-by-line):**
- `adapters/dependency_injection.py` — the composition root; **multi-tenant `for_tenant()` eviction
  and container lifecycle/`close()` is the single riskiest code** (documented: eviction may `close()`
  a container still referenced by a caller). Verify eviction safety, `reset_default()`,
  `bootstrap()`'s in-event-loop guard, `health()` shape, and `evaluate_drift()` telemetry.
- `infrastructure/bounded_executor.py` — semaphore/zombie accounting, re-entrancy guard, sync/async
  parity, load-shed path.
- `infrastructure/lfu_cache.py` — O(1) LFU eviction correctness, TTL sweeper, thread safety.
- `infrastructure/circuit_breaker.py` — CLOSED/OPEN/HALF_OPEN transitions, single-flight probe.
- `infrastructure/http_contract_repository.py` — snapshot atomicity, TOCTOU/symlink/owner checks,
  envelope validation, response byte cap, per-scope path hashing.
- `usecases/sync_contracts_usecase.py` — single-flight boot lock, jitter, prime-in-place (never
  clear-then-refill), breaker fallback.
- `usecases/validate_contract_usecase.py` — size guards (bytes vs chars), schema resolution, the
  telemetry-before-raise ordering, fail-mode handling.
- `domain/validator.py` — the six rules' correctness; the documented `CompositeValidator`-runs-semantic-
  validator-on-non-dict-payload latent issue; the dual schema vocabulary
  (`min`/`max`/`minimum`/`maximum`/`null_forbidden` enforced, `minLength`/`maxLength`/`format` silently
  ignored unless semantic validation is on).

---

# 7. PRIOR-AUDIT BASELINE TO RECONCILE (as of 2026-06-14 — VERIFY EACH)

Treat every row as a hypothesis. For each, output a status (Verified Present / Verified Fixed /
Partially Addressed / Unverified) with `file:line` evidence.

**Known bugs & debt:**
1. **Example contract/enum mismatch** — offline fallback returns `action="manual_review"`, not in the
   contract enum `["approve_return","reject_return","escalate"]`; under `mode="raise"` the "clean"
   scenario raises when no API key is set. `examples/LangChain/agent.py` vs
   `examples/LangChain/contracts/return_processing.json`. (MED)
2. **Multi-tenant LRU keyed on lookups, eviction `close()`s a possibly-live container** —
   `adapters/dependency_injection.py` (documented ~:84–118). (MED — top correctness risk)
3. **`requires-python` contradiction** — `>=3.11` vs 3.10 claimed in classifiers/ruff/CLAUDE.md.
   `pyproject.toml`. (MED)
4. **Size guards count characters, not bytes** — `len(json.dumps(...))` vs the byte-named budget.
   `usecases/validate_contract_usecase.py` (documented ~:127,145). (LOW)
5. **Stale docstring** — `TelemetryEvent` described as "mutable" though `frozen=True`.
   `domain/models.py`. (LOW)
6. **`pii_sanitize` uses stdlib `re`, not `re2`** — the one regex bypassing the project-wide rule.
   `pii_sanitize.py`. (LOW)
7. **`CompositeValidator` runs the semantic validator even on non-dict payloads** —
   `domain/validator.py` (documented ~:451–453). (LOW, latent)
8. **Dual schema vocabulary is implicit** — `minLength`/`maxLength`/`format` silently ignored unless
   semantic validation is on; easy to author a contract that looks enforced but isn't.
   `domain/validator.py` (documented ~:333–367). (MED)
9. **`ValidationTimer` retained as deprecated dead code** — emits `DeprecationWarning`, not wired by
   the container. `infrastructure/timer.py`. (LOW)

**Documented coverage gaps (verify they still exist):**
- No dedicated `test_container.py` for the composition root.
- `for_tenant()` LRU eviction at the max-tenants bound — untested.
- `reset_default()` tearing down the tenant registry — untested.
- `health()` aggregation shape — untested.
- `evaluate_drift()` publishing a `__drift__` telemetry event — untested.
- `bootstrap()`'s in-event-loop guard (raises `RuntimeError`) — untested.

**Documented "partial" areas (verify current status):** multi-tenant eviction lifecycle; drift is a
manual/opt-in library call (not auto-wired — this is *by design*, not a bug); telemetry ships to a
hard-coded path with no contract test.

---

# 8. STAGE 4 — SEVERITY & PRIORITIZATION RUBRIC

Classify every finding:

- **CRITICAL** — breaks a core guarantee or determinism, corrupts data, enables a security breach, or
  crashes the host under realistic conditions. (e.g. an LLM/nondeterminism in the hot path; a
  use-after-`close()` that stalls a live tenant; snapshot integrity bypass.)
- **HIGH** — a real correctness or security defect that will bite real users, or a missing test for a
  guarantee that is easy to regress. (e.g. eviction closing a live container; silent non-enforcement
  that creates false safety.)
- **MEDIUM** — a defect with limited blast radius or a clear workaround; important pre-1.0 polish.
- **LOW** — cosmetic, stylistic, or latent-but-currently-harmless.
- **INFO** — observations, not defects (design notes, future considerations).

**Health Scorecard states (per dimension):** `GREEN` (healthy, verified), `YELLOW` (works with caveats
/ gaps), `RED` (failing or unsafe), `UNKNOWN` (could not verify — say why). Every state needs a
one-line justification and evidence.

Rank findings by severity, then by fix-leverage (how much correctness/safety per unit effort).

---

# 9. STAGE 5 — DELIVERABLE 1: `PHASE0_AUDIT_AND_HEALTH.md`

Write this file to the repository (suggested path: repo root or `docs/audits/`). Use this structure:

```
# CONGINE PHASE 0 — AUDIT & HEALTH REPORT
Date: <today>  |  Baseline reconciled: 2026-06-14  |  Auditor: Claude Code

## 0. Executive Summary
- Overall Phase 0 readiness in 3–5 sentences (is it close to done? what's blocking?).
- Count of findings by severity. Top 3 things that must be fixed before MCP.

## 1. Health Scorecard
| Dimension | State | Evidence / one-line justification |
(build, tests, coverage, lint, types, security scan, deps, architecture, concurrency, config, docs)

## 2. Executable Health Check Results
- Exact commands run, exit status, trimmed output for each (build, tests, coverage, lint, types,
  bandit, pip-audit). Gaps where a tool was unavailable.
- Current test count vs documented baseline (~259/32). Coverage % overall and for hot-path modules.
- What changed since 2026-06-14 (VCS summary).

## 3. Architectural Integrity
- Import-direction analysis result; any layering violations; composition-root check; ports check.

## 4. Prior-Baseline Reconciliation
| # | Item | Status | Evidence (file:line) | Note |
(one row per §7 item; Verified Present / Verified Fixed / Partially Addressed / Unverified)

## 5. Findings (severity-ranked)
For each finding:
### [SEVERITY] <short title>
- Location: <file:line>
- Evidence: <what you observed — quote the relevant code/behavior>
- Impact: <what breaks, for whom, under what conditions>
- Confidence: <observed / inferred>
- Fix direction: <the smallest correct change; NO full code unless Execution Mode>
- Effort: <S/M/L>  |  Guarantee touched: <which of the 7, if any>

## 6. Guarantee Verification
- One line per guarantee (1–7): HOLDS / AT RISK / BROKEN / UNVERIFIED, with evidence and whether a
  test backs it.

## 7. Unverified / Open Questions
- Everything you could not determine and exactly why, so a human can close the gap.
```

---

# 10. STAGE 6 — DELIVERABLE 2: `PHASE0_COMPLETION_ROADMAP.md`

Derive this **from your findings** (not from assumptions). Write it to the repo. Structure:

```
# CONGINE PHASE 0 — COMPLETION ROADMAP
Date: <today>  |  Derived from: PHASE0_AUDIT_AND_HEALTH.md

## A. Definition of Done (Exit Criteria for Phase 0)
Phase 0 is COMPLETE when ALL of the following are true (adjust only if a finding justifies it):
1. All CRITICAL and HIGH findings are resolved.
2. All MEDIUM correctness/security debts are resolved or have a recorded, justified deferral.
3. Each of the seven hot-path guarantees holds AND is backed by at least one test.
4. The composition root (ServiceContainer) has direct tests: bootstrap in-loop guard, health()
   shape, evaluate_drift() event, reset_default(), and for_tenant() eviction safety.
5. Full test suite passes on the DECLARED Python floor; coverage for hot-path-critical modules meets
   an agreed bar (state the bar).
6. Linter / type checker / bandit / pip-audit are clean OR every exception is explicitly documented.
7. The 5-minute offline quickstart runs end-to-end exactly as documented.
8. Determinism preserved: no LLM/network/nondeterminism anywhere in the validation hot path.
9. A recorded decision on every deprecated/dead-code item (delete vs quarantine).
10. The dual-schema-vocabulary foot-gun is resolved: either the ignored keywords are enforced, or
    loading a contract that uses them emits a clear WARNING naming the unenforced keyword.

## B. Ordered Task List
For EACH task (dependency-ordered; earlier tasks unblock later ones):
### TASK P0-<n>: <title>
- Rationale: <which finding(s) this closes>
- Severity: <CRITICAL/HIGH/MED/LOW>
- Files: <exact paths>
- Change summary: <what to do, precisely, minimal-diff>
- Acceptance test: <the EXACT, runnable assertion that proves it's done — name a test to add/modify
  and what it must assert>
- Effort: <S/M/L>
- Depends on: <task IDs or "none">
- Risk if skipped: <one line>

## C. Suggested Sequence & Grouping
- A short critical-path ordering (what to do first, what can be batched).

## D. GO / NO-GO GATE FOR MCP (Phase 1)
A checklist that must be 100% green before ANY MCP work begins. If any item is red, MCP does not
start. (This is the boundary — do not design MCP here; only define the gate.)

## E. Out of Scope (explicitly NOT Phase 0)
- MCP server, CLI future commands, SQLite event store, agent adapters, arch graph, routing — list
  them so no one mistakes them for completion work.
```

Every acceptance test must be **objective and runnable** ("a multibyte payload one byte over
`max_payload_bytes` is rejected with an `INPUT_BOUNDS` error", not "size guard improved"). A roadmap
item without a concrete acceptance test is incomplete — fix it.

---

# 11. STAGE 7 — SELF-REVIEW (mandatory before finishing)

Before declaring done:
1. **Verify every `file:line`** you cited actually points at what you claim. Correct or downgrade any
   you cannot re-confirm.
2. **False-positive sweep.** Re-examine each CRITICAL/HIGH finding adversarially — could it be a
   misread? If confidence is not high, say so and explain.
3. **Coverage of the checklist.** Confirm you addressed all 14 dimensions and all §7 baseline items;
   list any you could not complete and why.
4. **Determinism & scope check.** Confirm no proposed fix introduces nondeterminism into the hot
   path, and no roadmap item strays past the MCP boundary.
5. **Reproducibility.** Confirm the health-check commands you ran are recorded exactly, so the audit
   can be re-run later.

---

# 12. WHAT NOT TO DO

- Do **not** modify code, config, or tests outside Execution Mode (§14).
- Do **not** trust the attached documents over the code.
- Do **not** invent `file:line`, test results, or bug statuses.
- Do **not** design or scaffold the MCP server or any later-phase feature.
- Do **not** propose LLM-based or nondeterministic "improvements" to validation.
- Do **not** refactor for taste, reformat unrelated code, or bundle unrelated changes.
- Do **not** hide uncertainty — surface it.

---

# 13. HANDLING UNCERTAINTY & STOP CONDITIONS

- If a health command fails or a tool is missing: record it as a health gap and continue; never abort
  the whole audit for one failure.
- If the repository layout differs materially from the baseline (e.g. modules moved/renamed): note the
  drift, adapt, and proceed from the code.
- If something is genuinely ambiguous and material to the roadmap: record it as an Open Question in
  Deliverable 1 and make the roadmap item conditional on resolving it, rather than guessing.
- When both deliverables are written and self-reviewed, stop and report the summary (§15). Do not
  begin fixing anything.

---

# 14. OPTIONAL EXECUTION MODE (OFF BY DEFAULT — enable only on explicit operator instruction)

Do **nothing** in this section unless the operator has said, in plain words, to enter Execution Mode
(e.g. "Execution Mode: implement the Phase 0 roadmap"). When enabled:

1. Work **one roadmap task at a time**, in the roadmap's dependency order, starting with the highest
   severity.
2. For each task: make the **minimal** change; add/adjust the task's **acceptance test**; run the
   **full test suite**; confirm green before moving on. If a change regresses any test or any of the
   seven guarantees, **revert and stop**, reporting what happened.
3. **Never** cross the MCP boundary or start any later-phase feature.
4. **Never** introduce nondeterminism into the hot path.
5. After each task, report: what changed (files + diff summary), the acceptance test result, and the
   updated gate status. Pause for the operator between tasks unless told to proceed continuously.
6. Keep the two report files updated as tasks complete (mark items done, update the gate check).

---

# 15. FINAL OUTPUT (report this back in the chat when done)

- The two file paths written (`PHASE0_AUDIT_AND_HEALTH.md`, `PHASE0_COMPLETION_ROADMAP.md`).
- The health scorecard at a glance.
- Findings count by severity, and the top 3 blockers to MCP.
- The single most important thing to fix first, and why.
- Any Open Questions that need a human decision before the roadmap can be executed.

```text
=== END PROMPT (stop copying here) ===
```

---

## FOOTER — TIPS FOR YOU (the founder)

- **Run it in audit mode first, read both artifacts, *then* decide on Execution Mode.** The prompt
  defaults to read-only for exactly this reason — you want to see the true state before anything
  changes.
- **If Claude Code says an item is "Unverified,"** that's a feature, not a failure — it's telling you
  where it couldn't get certainty (often a missing tool or an ambiguous spec). Resolve those and
  re-run; the prompt is designed to be re-runnable.
- **Attach at least `01_SYSTEM_STATE.md`, `04_PHASE_ROADMAP.md`, my `05_IMPLEMENTATION_ROADMAP.md`,
  and `CONGINE_MENTAL_MODEL.md`.** The first two give the Phase 0 baseline to reconcile; the third
  defines exactly where Phase 0 ends and MCP begins (so it doesn't scope-creep); the fourth carries
  the determinism principle that must not be violated.
- **When Phase 0's gate is green,** the newer `05_IMPLEMENTATION_ROADMAP.md` (Phase B) is your next
  prompt's basis for the MCP server — but not before the gate passes.
