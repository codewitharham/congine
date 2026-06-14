# QUICKSTART VALIDATION

## Can a New Developer Integrate Congine in 5 Minutes?

Generated: 2026-06-14
Derived from the actual API (`congine_core/__init__.py`, `adapters/guard.py`, `adapters/dependency_injection.py`, `config.py`) and the working example under `examples/LangChain/`.

The fastest path to "it works on my machine" is the **standalone / offline** topology: local contract files, telemetry off, no control plane. This exercises the real validation engine with zero infrastructure.

---

### Step 1: Install

```bash
# from the workspace root
uv sync --package congine-sdk
# or, as a consumer of the published package:
pip install congine-sdk
```

Core deps pulled automatically: `google-re2`, `httpx`, `jsonschema`, `portalocker`. No extras needed for the rule engine.

> Caveat: `pyproject.toml` currently pins `requires-python = ">=3.11"` even though the project otherwise claims 3.10 (see `01_SYSTEM_STATE.md` debt #3). Use Python ≥3.11 until that is reconciled.

---

### Step 2: Configure (standalone, no control plane)

```bash
export CONGINE_LOCAL_CONTRACTS_DIR=./contracts   # binds FileContractRepository, no sync daemon
export CONGINE_TELEMETRY_ENABLED=false           # NoOpEventBus, no drain thread, no network
```

That is the complete required configuration for offline use. `base_url` defaults to `http://localhost:8080` and is treated as local, so the non-local HTTPS/credential policy in `CongineConfig.validate()` does not apply.

---

### Step 3: Define a Contract

`./contracts/sentiment.json` — the simplest contract the **rule engine** fully enforces (object, required field, type, enum):

```json
{
  "id": "sentiment-v1",
  "schema": {
    "type": "object",
    "properties": {
      "label": { "type": "string", "enum": ["positive", "negative", "neutral"] },
      "score": { "type": "number", "minimum": 0, "maximum": 1 }
    },
    "required": ["label", "score"]
  }
}
```

> The rule engine vocabulary is: `required`, `properties[].type`, `enum`, `min`/`max` **and** `minimum`/`maximum`, `pattern` (anchored, RE2), and top-level `null_forbidden`. It does **not** enforce `minLength`/`maxLength`/`format` unless you also set `CONGINE_SEMANTIC_VALIDATION=true` (which adds the jsonschema validator). Authoring `minLength` and expecting enforcement under default config is the most common foot-gun (see `01_SYSTEM_STATE.md` debt #8).

---

### Step 4: Apply the Guard

```python
from congine_core import ServiceContainer
from congine_core.adapters import congine_guard

container = ServiceContainer.from_env()   # reads CONGINE_* env
container.bootstrap()                      # primes cache from ./contracts (one-shot, no network)

@congine_guard("sentiment-v1", container=container, mode="raise")
def classify(text: str) -> dict:
    return {"label": "positive", "score": 0.92}   # replace with your LLM call
```

---

### Step 5: Run It

```python
print(classify("great product"))          # passes -> returns {"label": "positive", "score": 0.92}

# A violation (score out of range) under mode="raise":
@congine_guard("sentiment-v1", container=container, mode="raise")
def bad(text: str) -> dict:
    return {"label": "positive", "score": 9.9}

try:
    bad("x")
except Exception as e:                      # CongineValidationError
    print("blocked:", e)                    # -> "Contract sentiment-v1 validation failed"
finally:
    container.close()
```

- **`mode="envelope"`** (default) returns `{"output": ..., "validation_result": ...}`; check `result["validation_result"].is_pass()` and `.breaches`.
- **`mode="output"`** returns the raw output (validation still runs; enforcement via `fail_mode`).
- **`mode="raise"`** raises `CongineValidationError` on failure.

What success looks like: the passing call returns normally; the failing call raises (or, in `envelope` mode, returns `is_pass()==False` with a populated `breaches` tuple).

---

## Gaps Found (things that would trip up a new developer)

1. **Cold-start with no contracts = hard error, not a no-op.** If the contract isn't in the cache (bad `CONGINE_LOCAL_CONTRACTS_DIR`, empty dir, or HTTP boot with a dead plane and no snapshot), the first guarded call raises `CongineContractNotFoundError` from `_resolve_schema` (`usecases/validate_contract_usecase.py:161-166`). `bootstrap()` returns the count loaded — **check it's > 0**. There is no startup assertion that the contract you guard against actually loaded.

2. **`minLength`/`maxLength`/`format` silently unenforced by default.** The shipped example `support.reply.text` contract uses `minLength`/`maxLength`; under default config those are ignored, so the streaming demo "passes" without enforcing length. Set `CONGINE_SEMANTIC_VALIDATION=true` to enforce full JSON Schema. (`01_SYSTEM_STATE.md` debt #8.)

3. **The example does not run cleanly offline.** `examples/LangChain/agent.py` with `mode="raise"` and no `GOOGLE_API_KEY` returns `action="manual_review"`, which violates the contract enum and raises in the "clean" scenario (`01_SYSTEM_STATE.md` debt #1). A newcomer copying the example will hit a confusing exception. Fix per roadmap P0-2.

4. **`requires-python` blocks Python 3.10** despite docs claiming support (debt #3).

5. **`bootstrap()` must not be called inside a running event loop** — it raises `RuntimeError` and directs you to `await bootstrap_async()` (`dependency_injection.py:271-278`). Async apps (FastAPI startup, notebooks) need the async variant. This is correct behavior but easy to hit unexpectedly.

6. **No `pip install`-time entry point yet.** There is no `congine` CLI (Phase 1B), so the only integration path today is Python-level (`@congine_guard` / `ServiceContainer`). Git-hook / CI usage is not yet possible out of the box.

7. **Non-dict outputs need an `extractor`.** Guarding a function that returns a string/Pydantic model without `extractor=` validates the raw object; the rule engine then fails it as "Payload must be an object/dict" (`domain/validator.py:384-395`). Pass `extractor=lambda s: {"text": s}` for string completions.

**Verdict:** a developer who knows to use the standalone topology and the rule-engine vocabulary can integrate in ~5 minutes. The two things most likely to cost them the other 25 minutes are the silent `minLength` gap (#2) and the cold-start `ContractNotFound` (#1). Both are documentation/guard-rail fixes, not architecture problems.
