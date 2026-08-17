# 12 — Founder Decision Register

This file records the recommended final answers to the 17 founder questions surfaced by the evidence. These should be converted into ADRs after repository verification.

| Q | Topic | Recommended enterprise decision |
|---|---|---|
| Q1 | Why hexagonal architecture? | Keep it. Record rationale: isolate deterministic core, replace infrastructure, enable peripheral growth, improve testability. |
| Q2 | Runtime Protocol checks? | Yes at composition boundaries, in addition to blocking mypy. |
| Q3 | Untimed re-entrant inline execution? | Accept for now as a documented/instrumented exception; do not add complexity without evidence. |
| Q4 | Why only the native subset? | Define it as the fast deterministic subset; selectively add cheap/high-value rules, not full JSON Schema by default. |
| Q5 | Unknown type names? | Reject contract at admission/load time. |
| Q6 | `pattern=fullmatch`? | Preserve existing v1 meaning; introduce versioned future semantics rather than silently changing it. |
| Q7 | Third status? | Add `is_enforced()` now; long term separate evaluation state, conformance, and enforcement action. |
| Q8 | stdlib `re` in sanitizer? | Replace with RE2 unless current code proves a technical incompatibility. |
| Q9 | Windows production? | Development/testing only until security parity and mandatory Windows CI exist. |
| Q10 | Regional URLs real? | Never ship placeholders; require explicit base URL until real endpoints are deployed/verified. |
| Q11 | Bad boolean env values? | Raise configuration error. |
| Q12 | Keep `timer.py`? | Delete if no external compatibility consumer exists. |
| Q13 | Public `find_unenforced_keywords`? | Export now; later subsume into contract compiler/admission API. |
| Q14 | Health via port? | Yes; call `IValidationRunner.health()`. |
| Q15 | Timeout scale with semantic validation? | Separate backend budgets + admission complexity; do not blindly raise global timeout. |
| Q16 | mypy blocking? | Yes. |
| Q17 | 15ms vs 100ms timeout? | Eliminate duplicated defaults; one source of truth. |

## Additional decisions added by this package

1. Contract language must become explicitly versioned before breaking semantic changes.
2. Dotted property paths should be rejected/flagged until an explicit path language exists.
3. Durable events must be schema-versioned from the start.
4. Evidence durability and best-effort telemetry must be separable concepts.
5. Tenant identity must be structural in durable keys/queries.
6. MCP is an early-feedback surface; CI remains the authoritative repository boundary where needed.
7. Multi-agent adaptation uses adapters + statistics, not model training in the core.
8. Business Policy DSL is a future authoring layer compiling to deterministic IR, not a runtime AI judge.
