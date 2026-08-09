# ARCHITECTURE_CURRENT — progress ledger

Commit: `a561992` (+ uncommitted working tree) · Branch `ahmed-main-v2` · Started 2026-08-09

Pass files are written as the **final document's section bodies**; Pass 16 concatenates them
into `docs/architecture/ARCHITECTURE_CURRENT.md` with the front matter, §0, §1, §17 and appendices.

| Pass | Title | Status | Output file | Maps to § | Notes |
|------|-------|--------|-------------|-----------|-------|
| 1 | Inventory & drift reconciliation | DONE | arch_pass_1.md | §2 | 37 files today / 36 at baseline; 33-vs-36 resolved; P0-1 landed (committed), P0-2 landed (uncommitted) |
| 2 | Layer model as it is | DONE | arch_pass_2.md | §3 | 3 arguable placements documented |
| 3 | Dependency graph, verified | DONE | arch_pass_3.md | §4 | AST analysis, runtime vs TYPE_CHECKING; 0 violations, 1 near-miss |
| 4 | Ports & adapters catalogue | DONE | arch_pass_4.md | §5 | 7 ports + IValidator; exact signatures |
| 5 | Composition & wiring map | DONE | arch_pass_5.md | §6 | every branch in `ServiceContainer.__init__` |
| 6 | Lifecycle | DONE | arch_pass_6.md | §7 | construction order, bootstrap, teardown, registries |
| 7 | Control flows | DONE | arch_pass_7.md | §8 | 5 step-numbered traces |
| 8 | Failure paths | DONE | arch_pass_8.md | §9 | 22 failure modes enumerated |
| 9 | Concurrency & state | DONE | arch_pass_9.md | §10 | 4 thread kinds, 7 locks, shared state table |
| 10 | Data model | DONE | arch_pass_10.md | §11 | 4 value objects, all frozen |
| 11 | Configuration surface | DONE | arch_pass_11.md | §12 | 46 fields / 46 env vars; 1 dead configurable |
| 12 | Contract semantics | DONE | arch_pass_12.md | §13 | safety-critical; empirically probed |
| 13 | Invariants & guarantees | DONE | arch_pass_13.md | §14 | 7 documented + 4 discovered |
| 14 | Extension seams | DONE | arch_pass_14.md | §15 | 8 planned capabilities, all confirmed absent |
| 15 | Debt register | DONE | arch_pass_15.md | §16 | 9 prior debts re-verified + 12 new |
| 16 | Assembly | DONE | docs/architecture/ARCHITECTURE_CURRENT.md | — | COMPLETE — 3 804 lines, ~35 300 words, 100 tables, 7 mermaid diagrams |

Front matter, §0, §1, §17 and both appendices live in `arch_head.md` / `arch_tail.md`.
Assembly command: `cat arch_head.md`, then `arch_pass_1..15.md` separated by `---`, then `arch_tail.md`.

## Verification commands used

```bash
# module inventory
find libs/congine-sdk/src -name "*.py" | sort
git ls-tree -r --name-only 051ceae -- libs/congine-sdk/src/congine_core | grep '\.py$'
# import graph (runtime vs TYPE_CHECKING, via ast)  -> see arch_pass_3.md
# audit IDs
grep -rnoE "(FIX-[0-9]+|audit [A-Z][0-9-]*|\bH[1-4]\b|\bM[2-5]\b|\bD-[0-9]+\b|\bC2\b|\bL[4-7]\b|P0-[0-9]|F-[0-9])" libs/congine-sdk/src/
# test suite
uv run --package congine-sdk --extra langchain --extra stats --extra dev pytest libs/congine-sdk/tests -q
#   -> 293 passed, 1 skipped in 22.70s
```
