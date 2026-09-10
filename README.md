# Congine

**Deterministic governance for AI-assisted software development.**

> The agent may propose. Congine decides.

Congine is an enforcement layer between AI coding agents and the systems that have to stay coherent.
Organizational rules are written by engineers as machine-readable contracts. Every governed output is
evaluated against the applicable contract by a rule engine written in ordinary code — no model sits on
the verdict path. Given the same input, contract, evaluator version and configuration, the verdict is
the same every time.

**Probabilistic authoring, deterministic enforcement.**

---

> ### ⚠️ Status: pre-release. Not published, not production-ready.
>
> The core engine exists and is heavily hardened. It is **not** on PyPI, and packaging/clean-install
> truth is not yet proven. There is no MCP server, no CLI, no control plane and no persistence.
> Install from source only. See [What exists today](#what-exists-today).

---

## Why this exists

AI coding agents made code generation elastic. Code review did not become elastic with it.

The gap is not that agents write code that fails to run — modern agents write code that runs. The gap
is that **functional correctness and organizational correctness are different properties**:

| | Functional correctness | Organizational correctness |
|---|---|---|
| Asks | Does this do what was requested? | Does this respect *our* rules? |
| Defined by | The task | Your architecture, contracts, conventions, regulatory position |
| Checked by | Tests, CI, the agent itself | Human review, tribal memory, a wiki nobody opens |
| Fails | Loudly | **Silently — it ships, it works, and it is wrong** |

An agent cannot infer a rule it was never told exists. Accumulated across a team, those individually
minor deviations become architectural drift discovered a year later during an audit or a migration.

Existing tools do not close this. Linters know the language, not your layering. Scanners know CVE
classes, not your data contracts. Guardrail products know toxicity, not your approved dependency set.
And "use an AI to check the AI" fails for a structural reason: **a verdict that varies between
identical inputs cannot become policy.** It cannot be audited, appealed, or defended to a regulator.

## What Congine is — and is not

| It is not | It is |
|---|---|
| A coding assistant | The policy layer governing what assistants may produce |
| A prompt library | A contract system — human-authored, versioned, reviewed like code |
| A generic AI guardrail | Enforcement for **your** architecture and **your** contracts |
| Another probabilistic model | A deterministic evaluator: same input, same verdict |
| An LLM evaluator, authorization platform, or static analyzer | Adjacent categories, not this thesis |

## What exists today

| Capability | Status |
|---|---|
| Deterministic rule engine + contract validation | ✅ Available |
| `@congine_guard` decorator (sync + async) | ✅ Available |
| Contract admission — refuses unsafe/unenforceable contracts at load | ✅ Available |
| Fail-closed result semantics (`is_enforced()`, typed `DegradedReason`) | ✅ Available |
| Bounded execution, load shedding, circuit breaker, LFU schema cache | ✅ Available |
| Offline / standalone operation | ✅ Available |
| Multi-tenant isolation | ✅ Available |
| LangChain callback integration | ⚠️ Partial — output-completeness boundary in progress |
| Semantic (full JSON Schema) validation | ⚠️ Optional, staged budgets |
| Published package on PyPI | ❌ Not yet |
| CLI | ❌ Planned |
| MCP server | ❌ Planned |
| Durable evidence / history | ❌ Planned |
| Control plane | ❌ Planned |

Anything marked ❌ does not exist. This README will not tell you how to use it.

## Install

**Not on PyPI yet.** From source:

```bash
git clone https://github.com/codewitharham/congine.git
cd congine
uv sync --all-extras
```

Requires **Python ≥ 3.11**.

## Quickstart — offline, no control plane

The fastest honest path. Contracts come from a local directory; nothing leaves your machine.

**1. Write a contract** — `contracts/support-reply.json`:

```json
{
  "id": "support.reply",
  "schema": {
    "type": "object",
    "required": ["intent", "confidence"],
    "properties": {
      "intent":     { "type": "string", "enum": ["refund", "escalate", "answer"] },
      "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
    }
  }
}
```

**2. Point Congine at it and guard a function:**

```python
import os
os.environ["CONGINE_LOCAL_CONTRACTS_DIR"] = "./contracts"
os.environ["CONGINE_TELEMETRY_ENABLED"] = "false"

from congine_core import ServiceContainer, congine_guard, CongineValidationError

with ServiceContainer.from_env() as container:
    loaded = container.bootstrap()
    assert loaded > 0, "no contracts loaded — check CONGINE_LOCAL_CONTRACTS_DIR"

    @congine_guard("support.reply", container=container, mode="raise")
    def classify(text: str) -> dict:
        return {"intent": "refund", "confidence": 0.91}   # your model call here

    print(classify("I want my money back"))               # passes

    @congine_guard("support.reply", container=container, mode="raise")
    def bad(text: str) -> dict:
        return {"intent": "refund", "confidence": 9.9}    # out of range

    try:
        bad("...")
    except CongineValidationError as e:
        print("blocked:", e)                              # the point of the product
```

> **Check `bootstrap()`'s return value.** If it is `0`, no contracts loaded and the first guarded call
> raises `CongineContractNotFoundError`.

### ⚠️ Contracts express more than the rule engine enforces

The rule engine reads a **specific, finite** keyword set. JSON Schema keywords outside it —
`minLength`, `format`, `const`, `items`, `allOf` and others — are **not evaluated by the rule engine**.
Contract admission refuses contracts whose declarations it cannot honour, but **read the contract
reference before authoring**, and enable semantic validation if you need full JSON Schema.

A contract that looks enforced and is not is exactly the failure this project exists to eliminate.

## Repository layout

```
libs/congine-sdk/     the engine — Python, hexagonal (L0 kernel → L5 adapters)
packages/             workspace packages
docs/                 architecture, analysis, phase records
CONGINE_PROGRESS.md   shared source of truth for system state and phases
```

Polyglot monorepo: **uv** for Python, **Nx** for orchestration.

## Development

```bash
npm ci
uv sync --all-extras

uv run --package congine-sdk --extra langchain --extra stats --extra dev \
  pytest libs/congine-sdk/tests -q
uv run --package congine-sdk ruff check libs/congine-sdk
uv run --package congine-sdk ruff format --check libs/congine-sdk

npx nx run-many -t lint test typecheck
```

## Engineering invariants

These are enforced, not aspirational. Changes that violate them are rejected.

1. **No model on the verdict path.** Verdicts come from code.
2. **Dependencies point inward only.** L5 → L4 → L3 → L2 → L1 → L0, gated in CI.
3. **Fail closed.** If the system cannot completely and safely evaluate an output, it does not report
   conformance.
4. **No silent non-enforcement.** Anything the engine cannot enforce is refused or reported — never
   quietly skipped.
5. **One composition root.** Concretes are constructed in exactly one place.

## Security

See [SECURITY.md](SECURITY.md) for supported versions, scope, and how to report a vulnerability.

## License

[Apache-2.0](LICENSE)
