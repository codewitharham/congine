# LangChain × congine-sdk — worked example

A runnable agent that uses **deepagents + Google Gemini** for the LLM work and
**congine-sdk** as a *hot-path guard* on the model's output. It demonstrates the
SDK's two entry points side by side and shows both a **passing** validation and a
**blocked breach**.

> `congine-sdk` validates an LLM/agent's output against a versioned contract and
> degrades/blocks/heals it **before** the payload reaches your business logic.

---

## What it shows

| # | Entry point | File ref | Pass case | Breach case |
|---|-------------|----------|-----------|-------------|
| A | `@congine_guard` decorator | [`agent.py`](agent.py) `extract_weather` / `process_return` | weather dict validates | `confidence_score=1.5` → `RANGE_CHECK`, guard raises `CongineValidationError` |
| B | `CongineCallbackHandler` | [`agent.py`](agent.py) `demo_callback_handler` | streamed reply validates | empty completion → `minLength` breach |
| C | live deepagents + Gemini | [`agent.py`](agent.py) `demo_live_agent` | agent runs, output guarded | (optional; needs a real key) |

---

## Prerequisites

- The repo is a **uv workspace**; this example is already a member
  (`libs/congine-sdk/examples/LangChain` in the root `pyproject.toml`).
- A Google Gemini API key **only** for the live agent (section C). Sections A and
  B run fully offline.

## Setup & run

From the **workspace root** (`congine_workspace/`):

```bash
uv sync                                   # installs deepagents, langchain-google-genai, the SDK, …
# put a real key in libs/congine-sdk/examples/LangChain/.env  ->  GOOGLE_API_KEY=...
uv run --package congine-langchain-example python libs/congine-sdk/examples/LangChain/agent.py
```

### Expected output (abridged)

```
[bootstrap] loaded 3 contract(s) from ...\contracts
=== A. @congine_guard (structured output) ===
[pass] extract_weather('Paris')
   is_pass()  : True  (status=pass, 0.1x ms)
[breach] process_return('TKT-0001') -> expect a block
   blocked by guard: Contract customer.support.return_processing validation failed
      - [RANGE_CHECK] field='confidence_score': Value for 'confidence_score' is above maximum 1.0
=== B. CongineCallbackHandler (streamed text) ===
[pass] ... -> is_pass()=True
[breach] empty completion -> is_pass()=False
      - [<semantic>] field='text': ... shorter than 1 ...
[shutdown] container closed.
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

### 3. Decorator vs. callback handler — pick by output shape
- **`@congine_guard`** → use when your function returns **structured output** (a
  dict / multi-field object). It validates the whole dict against the contract.
  Best fit for the weather and return contracts.
- **`CongineCallbackHandler`** → use for **streamed free text**. It joins the
  tokens and validates `{"text": <completion>}` — a **single field**. That is why
  it needs a *text-shaped* contract (`support.reply.text`); pointing it at a
  multi-field contract would always breach on the missing fields.

### 4. `fail_mode=degrade` + guard `mode="raise"` (layered enforcement)
Enforcement happens at two layers:
- **`CONGINE_FAIL_MODE`** governs the *use case*: `degrade` makes it **return** a
  failed `ValidationResult` (so the callback handler can read `.breaches`);
  `strict` would make it **raise** (and the handler would swallow that, leaving
  `last_result = None`).
- **guard `mode`** governs the *decorator*: `mode="raise"` blocks on a breach;
  `"envelope"` returns `{"output", "validation_result"}`; `"output"` returns the
  raw value.

We use `degrade` globally and `mode="raise"` on `process_return`, so the
decorator blocks **and** the handler can surface breach details.

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
| `GOOGLE_API_KEY` | *(your key)* | Gemini; only the live agent (C) needs it |
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
