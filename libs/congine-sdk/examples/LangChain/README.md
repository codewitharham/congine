# LangChain × congine-sdk — worked example

A runnable return-processing agent that uses **Google Gemini** when configured
and a deterministic local fallback otherwise. **congine-sdk** guards the
structured return decision and validates a streamed support reply before either
result reaches downstream code.

> `congine-sdk` validates an LLM/agent's output against a versioned contract and
> degrades/blocks/heals it **before** the payload reaches your business logic.

---

## What it shows

| # | Entry point | File ref | Demonstrated behavior |
|---|-------------|----------|-----------------------|
| A | `@congine_guard` decorator | [`agent.py`](agent.py) `process_untrusted_customer_ticket` | validates normal and adversarial-prompt return decisions against `customer.support.return_processing` |
| B | `CongineCallbackHandler` | [`agent.py`](agent.py) `run_real_world_scenarios` | joins five streamed tokens and validates the reply against `support.reply.text` |
| C | offline CI runner | [`smoke.py`](smoke.py) | clears the Google key, disables remote services, executes the guarded fallback, and asserts the contract-valid `escalate` decision |

---

## Prerequisites

- The repo is a **uv workspace**; this example is already a member
  (`libs/congine-sdk/examples/LangChain` in the root `pyproject.toml`).
- A Google Gemini API key is optional. Without one, both structured scenarios
  use the contract-valid local `escalate` fallback; the streamed reply is always
  local.

## Setup & run

From the **workspace root** (`congine_workspace/`):

```bash
uv sync                                   # installs LangChain, the Gemini provider, the SDK, …
# put a real key in libs/congine-sdk/examples/LangChain/.env  ->  GOOGLE_API_KEY=...
uv run --package congine-langchain-example python libs/congine-sdk/examples/LangChain/agent.py
```

For the deterministic offline CI path (no API key, telemetry, or network), run:

```bash
uv run --package congine-langchain-example python libs/congine-sdk/examples/LangChain/smoke.py
```

### Expected offline smoke output

```
LangChain example smoke passed (offline fallback validated).
```

---

## Guidelines & the reasoning behind each choice

### 1. Contract files must use the key `"id"` (not `"contract_id"`)
The file loader (`FileContractRepository._extract`) only recognises a contract
object that has **`"id"` and `"schema"`**, and the cache is keyed on `id`. A file
using `"contract_id"` loads as **zero contracts** and every guarded call then
raises `CongineContractNotFoundError`. The `@congine_guard(contract_id=...)`
argument must equal that JSON `"id"`. `version`/`fail_mode` inside a file are
**ignored** by the file loader — policy comes from the env (`CONGINE_FAIL_MODE`).

```jsonc
// contracts/weather_policy.json
{ "id": "analytics.weather.extraction", "schema": { /* JSON Schema */ } }
```

### 2. One container, bootstrapped once, closed on exit
`ServiceContainer` is the composition root and owns all background daemons + the
bounded validation pool. Build it once, `bootstrap()` to prime the schema cache
(returns the count — we assert it), share it, and `close()` on shutdown. We pass
`container=` explicitly to the guard and the handler rather than relying on the
process-wide default.

`close()` is terminal and idempotent. Reusing the container through a guard or
callback after shutdown raises `CongineLifecycleError`; create and bootstrap a
new container instead. Process-wide and tenant registries likewise replace a
closed cached instance rather than returning it.

### 3. Decorator vs. callback handler — pick by output shape
- **`@congine_guard`** → use when your function returns **structured output** (a
  dict / multi-field object). It validates the whole dict against the contract.
  This is what protects `process_untrusted_customer_ticket`.
- **`CongineCallbackHandler`** → use for **streamed free text**. It joins the
  tokens and validates `{"text": <completion>}` — a **single field**. That is why
  it needs a *text-shaped* contract (`support.reply.text`); pointing it at a
  multi-field contract would always breach on the missing fields.

### 4. `fail_mode=degrade` + guard `mode="raise"` (layered enforcement)
Enforcement happens at two layers:
- **`CONGINE_FAIL_MODE`** governs the *use case*: `degrade` makes it **return** a
  failed `ValidationResult` (so the callback handler can read `.breaches`);
  `strict` makes it **raise**, and the callback handler propagates every
  `CongineBaseException` so policy failures cannot be neutralised by the
  integration surface.
- **guard `mode`** governs the *decorator*: `mode="raise"` blocks on a breach;
  `"envelope"` returns `{"output", "validation_result"}`; `"output"` returns the
  raw value.

We use `degrade` globally and `mode="raise"` on
`process_untrusted_customer_ticket`, so the decorator blocks a failed result
while the callback handler can expose a failed result for inspection.

Unexpected non-SDK callback failures are still logged and contained, returning
`None`. The handler publishes `last_result` and its per-run result history under
one lock, so concurrent LangChain callback threads observe a consistent state.

### 5. Semantic validation is ON for full JSON Schema
The pure `RuleEngine` covers `required` / `type` / `enum` / **range**
(`minimum`/`maximum`) / regex `pattern`. String-length keywords
(`minLength`/`maxLength`) are only enforced when
`CONGINE_SEMANTIC_VALIDATION=true`, which composes the JSON-Schema semantic
validator on top. We enable it so `support.reply.text`'s `minLength` actually
bites.

### 6. Offline by construction
`CONGINE_LOCAL_CONTRACTS_DIR` binds a `FileContractRepository` (no control-plane
polling, sync worker unallocated) and `CONGINE_TELEMETRY_ENABLED=false` swaps in
`NoOpEventBus` (no drain thread, no network). Together: a pure in-process
validator. `agent.py` also resolves the relative `./contracts` path to an
absolute one so it runs from any cwd.

---

## Env-var reference (this example's `.env`)

| Var | Value here | Why |
|-----|-----------|-----|
| `GOOGLE_API_KEY` | *(your key)* | Enables the optional live Gemini path in `agent.py`; leave empty for the fallback |
| `CONGINE_BASE_URL` | `http://localhost:8080` | loopback ⇒ offline, no credential enforcement |
| `CONGINE_FAIL_MODE` | `degrade` | use case returns failed results (see §4) |
| `CONGINE_SEMANTIC_VALIDATION` | `true` | enable `minLength`/`maxLength`/full JSON Schema (§5) |
| `CONGINE_LOCAL_CONTRACTS_DIR` | `./contracts` | offline file repo (§6) |
| `CONGINE_TELEMETRY_ENABLED` | `false` | no telemetry drain/network (§6) |
| `CONGINE_TIMEOUT_MS` | `150` | hard validation latency ceiling |
| `CONGINE_MAX_PAYLOAD_BYTES` | `1048576` | 1 MiB cap on a validated payload |

---

## Security note

`.env` is **gitignored**. If a real `GOOGLE_API_KEY` was ever committed here,
**rotate it** — it is already on disk and in shell history. Never commit real
keys.
