# P1 Pre-Change Verification

Date: 2026-08-21  
Branch: `P0_CLOSED_PHASE0`  
HEAD: `1258a982b7dca2caac38de07256a8339575edbf6`

## Authority and scope

This report starts the remaining Phase 1 structural-hardening work after P0 closure. Evidence is reconciled in this order:

1. current repository behavior;
2. the final P0 closeout and post-P0 mental model;
3. the historical Phase 0 dossier;
4. the pre-P0 GAP1-GAP4 snapshots at commit `49a2f93`.

The active scope is P1 only: blocking static gates, runtime port checks, transactional composition and bounded lifecycle, RE2-safe PII sanitization, dead timer cleanup, LangChain callback safety, executable example coverage, and narrow documentation updates. P1.5, P2, P3, schema-storage admission/versioning, partial-enforcement metadata, and full architecture-document reconciliation are deferred.

## Repository state

The initial worktree contained only three user-owned deletions:

- `libs/congine-sdk/SDK_AUDIT_Antigravity_Gemini3.1_pro.md`
- `libs/congine-sdk/SDK_AUDIT_Antigravity_Gemini3.5_Flash.md`
- `libs/congine-sdk/SDK_AUDIT_Cursor.md`

They must not be restored, staged, or otherwise modified by P1. All P1 changes will remain uncommitted.

## Measured baseline

- Full SDK tests: **478 passed, 1 skipped**.
- Ruff formatting: **84 files formatted**.
- Ruff checks: **all checks passed**.
- Default whole-SDK mypy probe: **74 errors in 19 files**.
- Strict production-source mypy probe: **4 errors in 2 files**.
- Strict whole-SDK mypy probe: **231 errors in 34 files**.
- Determinism and P0 closeout evidence remain authoritative at the final 478/1 snapshot, not the earlier 436/1 or GAP4 350/1 snapshots.

The four strict production-source errors are confined to `jsonschema_validator.py` and `dependency_injection.py`: one obsolete ignore, one validator-class typing issue, one missing `weakref.finalize` generic parameter, and one nullable contracts-directory flow issue.

## Nx and dependency preflight

`npm ci` completed from the checked-in lockfile after a registry reset required a cache-first retry. It did not change package metadata. Nx post-install scripts were run explicitly because the local npm policy skipped them.

With `NX_DAEMON=false`:

- `npm exec nx -- show projects --json` resolves exactly `congine-sdk`;
- the resolved project currently has `lint` and `test` targets only;
- `lint` runs Ruff formatting and checks through the SDK `uv` package;
- `test` runs the SDK pytest suite with the `langchain`, `stats`, and `dev` extras.

The install reported seven high-severity npm audit findings. Dependency-audit remediation is explicitly P2 and will not be mixed into P1 or auto-fixed.

## Reconciled P1 backlog

| Item | Pre-change status | P1 action |
| --- | --- | --- |
| Blocking mypy | Non-blocking CI command; no configured target | Add strict production-source configuration and blocking Nx/CI target |
| Layer dependency gate | Missing | Add a separate AST-based Nx/CI gate |
| Runtime port checks | Protocols are runtime-checkable; constructors do not enforce them | Validate use-case and composite-validator boundaries |
| Transactional composition | Container can leak resources during partial construction | Roll back every acquired owner on failure |
| Lifecycle cleanup | Several owners register but do not unregister `atexit`; telemetry close can race shipping | Make shutdown terminal, idempotent, bounded, and race-safe |
| PII sanitization | Uses a stdlib-regex backreference | Replace with an equivalent RE2-compatible pattern |
| `ValidationTimer` | Deprecated, unwired, directly tested | Delete implementation, tests, and references |
| Admission facade/scanner | Completed during P0 | Do not reimplement |
| LangChain callback state | Result writes are not one atomic state transition; SDK exceptions are swallowed | Lock result state and propagate `CongineBaseException` |
| LangChain example | Offline fallback emits an invalid enum | Correct it and add an Nx/CI smoke target |

## Historical contradictions resolved

- P0 is closed at 478 passed/1 skipped; historical lower test counts are not current acceptance baselines.
- The master prompt's P0 implementation steps are satisfied history, not active work.
- Direct string configuration is centrally normalized after the final P0 fix, superseding an earlier closeout paragraph.
- Mypy cannot enforce import direction; P1 therefore requires a distinct architecture gate.
- P1-07's admission facade and scanner already shipped during P0.
- A direct engine substitution cannot compile the old sanitizer backreference; P1 uses the verified equivalent RE2-compatible pattern instead.

## Stop conditions

Implementation pauses rather than guessing if current code invalidates an agreed public behavior, a public API must break without a migration path, stored contracts would be reinterpreted, or the requested P1 work would require a P1.5/P2/P3 policy decision.
