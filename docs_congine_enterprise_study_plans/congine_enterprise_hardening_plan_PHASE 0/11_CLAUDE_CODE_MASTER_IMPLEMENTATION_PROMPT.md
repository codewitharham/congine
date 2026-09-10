# 11 — Master Prompt for Claude Code

Copy/paste the content below into Claude Code **together with this whole directory and the current CONGINE repository**.

---

## PROMPT

You are acting as the senior implementation engineer for CONGINE.

Your job is to implement the enterprise-hardening decisions contained in the `congine_enterprise_hardening_plan/` directory while preserving the existing deterministic core and repository architecture.

### Required reading order

Read fully before changing code:

1. `congine_enterprise_hardening_plan/README.md`
2. `00_EXECUTION_PROTOCOL_FOR_CLAUDE_CODE.md`
3. `01_ENTERPRISE_INVARIANTS_AND_ARCHITECTURAL_CONSTITUTION.md`
4. `02_VALIDATION_RESULT_AND_ENFORCEMENT_SEMANTICS.md`
5. `03_CONTRACT_LANGUAGE_COMPILER_AND_POLICY_IR.md`
6. `04_CORE_ARCHITECTURE_LIFECYCLE_CONFIG_HARDENING.md`
7. `05_SECURITY_SUPPLY_CHAIN_AND_PLATFORM_SUPPORT.md`
8. `06_EVIDENCE_EVENT_STORE_HISTORY_AND_CONTROL_PLANE.md`
9. `07_MCP_CLI_CI_MULTI_AGENT_AND_POLICY_PLATFORM.md`
10. `08_VERIFICATION_CI_RELEASE_ENGINEERING.md`
11. `09_IMPLEMENTATION_BACKLOG_AND_ACCEPTANCE_CRITERIA.md`
12. `10_DOCUMENTATION_RECONCILIATION_AND_ADR_PLAN.md`

Also read the repository's current architecture/debt/ADR/config documentation and the existing GAP1–GAP4 evidence if present.

### Prime directive

**Do not assume the package's historical line numbers or defect statuses are still current. Code at current HEAD is runtime truth. The package defines desired decisions, not permission to reintroduce an old state.**

### First task: READ-ONLY verification

Before editing:

1. Print branch, HEAD, working-tree status.
2. Run the full existing test suite.
3. Run current lint/format checks.
4. Locate every P0 item from `09_IMPLEMENTATION_BACKLOG_AND_ACCEPTANCE_CRITERIA.md`.
5. For each P0 item mark:
   - STILL PRESENT
   - ALREADY FIXED
   - CHANGED SHAPE
   - CANNOT VERIFY
6. Produce `docs/_suite/hardening/PRE_CHANGE_VERIFICATION.md` (or propose another repository-consistent path if `_suite` is inappropriate) with evidence and planned files.
7. Do not mutate production code until the report is complete.

### Implementation sequence

After verification, implement in this order unless current code proves a dependency requires adjustment:

#### P0 trust-critical

- finish `IValidationRunner`/health port boundary;
- fail closed on serialization/size measurement failure;
- eliminate silent dotted-path false safety;
- reject unknown type names during contract admission/load;
- add explicit `is_enforced()` or equivalent compatibility-safe evaluation-completeness signal;
- distinguish load shed from actual timeout with typed machine reason;
- make bool/mode/path config validation strict;
- centralize duplicated timeout default;
- remove/disable unconfirmed regional routing.

Each semantic change must have a reproducing test first or in the same commit.

#### P1 structural

- restore mypy as a blocking CI gate;
- add runtime port conformance at composition boundaries where safe;
- make composition-root construction failure-safe/transactional;
- improve deterministic lifecycle ownership, atexit unregister, telemetry shutdown ordering;
- switch PII sanitizer to RE2 if still applicable;
- remove dead `ValidationTimer` if no compatibility consumer exists;
- export `find_unenforced_keywords` and establish a contract-admission facade;
- fix executable examples and run them in CI.

#### P1.5 semantic-backend safety

- make semantic-validation performance warning honest;
- design separate native/semantic budget policy;
- introduce admission-time complexity checks experimentally;
- benchmark caching/precompilation options without sharing mutable validator instances until thread safety is proven.

#### P2 verification

- expose branch coverage;
- create determinism golden corpus;
- add Python support matrix and Linux release testing;
- add pip-audit/SBOM/security lint as appropriate;
- keep benchmark scripts reproducible.

### Architecture restrictions

Do not:

- add an LLM to runtime judgment;
- rewrite the rule engine for history/token/dashboard features;
- make MCP the only enforcement boundary;
- build production Control Plane persistence before durable evidence exists;
- implement Business Policy DSL now;
- add vector search before structured history requirements justify it;
- silently change v1 contract regex/path semantics without versioning/migration.

### Required design outcomes

Preserve these long-term seams even if only skeletons/interfaces are added now:

- distinct evaluation state vs conformance vs enforcement action;
- typed failure/degradation reasons;
- contract admission/compiler boundary;
- future contract-language versioning;
- future canonical `CompiledContract` / `PolicyIR` direction;
- versioned durable evidence event design;
- tenant-scoped data model;
- agent adapters as anti-corruption layers;
- deterministic correction hints;
- common semantics across SDK/MCP/CLI/CI.

### Commit discipline

Prefer small commits named by decision, e.g.:

```text
fix(validation): distinguish load shed from deadline timeout
fix(contracts): reject unknown type declarations at admission
fix(lifecycle): make container construction cleanup transactional
chore(types): restore blocking mypy gate
```

Do not commit generated lockfile/tool changes mixed with unrelated semantic fixes unless unavoidable.

### After each P0 commit

Run:

- focused tests;
- full tests;
- ruff;
- mypy once enabled;
- relevant executed examples;
- relevant measurement when performance/resource semantics changed.

Record results.

### Final reconciliation

After code stabilizes:

1. Reconcile `ARCHITECTURE_CURRENT.md` to new HEAD.
2. Correct §16 debt statuses while retaining stable IDs.
3. Replace obsolete §17 open questions with resolved decisions/current open decisions.
4. Patch stale D2/W1/V2 authoring prompts.
5. Add ADRs for decisions listed in `10_DOCUMENTATION_RECONCILIATION_AND_ADR_PLAN.md`.
6. Re-run the critical GAP3 examples and GAP4 measurements affected by changes.
7. Produce `POST_HARDENING_REPORT.md` containing:
   - commits;
   - changed semantics;
   - backward-compatibility notes;
   - tests/measurements;
   - remaining debt;
   - decisions deferred;
   - exact next roadmap phase.

### Stop conditions

Stop and ask the founder before proceeding if:

- a recommended change would break a documented external public API with no migration path;
- current HEAD materially contradicts the evidence and the correct decision is unclear;
- regional endpoint ownership/deployment cannot be verified;
- a contract-language change would silently reinterpret existing stored contracts;
- a persistence/security choice requires business/legal retention policy not present in the repository.

### Definition of done

Do not report success merely because tests are green.

A task is done only when:

- the dangerous state is no longer silent;
- the intended architectural boundary is enforced;
- machine-readable semantics are stable;
- regression tests exist;
- docs no longer contradict code;
- the next phase can build on the seam without rewriting the deterministic core.

---

## END PROMPT
