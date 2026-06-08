# Congine — Model Design & Training Strategy Blueprint

**Document type:** Engineering + ML + Product + GTM strategy. Internal & authoritative.
**Status:** The decisions in this document are committed. Future PRs and architecture conversations do not relitigate them without explicit founder sign-off.
**Inputs:** All four prior strategy documents (`phase0-congine-{newAudit, postSessionAudit, productionShippingRoadmap, sdkFirstBlueprint}.md`), the Phase 0–3 master plans (`AMCE_Phase0..3*.md` — note: AMCE was a working title; the product name is **Congine**), the live codebase at `libs/congine-sdk/`, and the user-confirmed answers to the four pivotal questions:

| Question | User answer |
|---|---|
| **Q1 — Product scope** | **1D — Hybrid: ship JSON healing (1A) now, expand to code-review (1B) by month 12** |
| **Q2 — Model architecture** | **2C — Hybrid: small fine-tuned classifier (Congine IP) + frontier model for actual fixes (rented)** |
| **Q3 — Inference deployment** | **3C — Both: open weights for self-host / air-gap, managed inference for velocity** |
| **Q4 — Training data source** | **4E — Hybrid layered: public + synthetic at v1, partnerships for depth, customer telemetry for the long-term flywheel** |

**Aim:** Give the team a single document that answers every question about what to build, how to train it, where the data comes from, how to evaluate it, how it ships, how it stays competitive when GPT-5 / Claude 5 / Llama 4 ships, and exactly what to do in the first four weeks to validate the entire plan before committing to a year of model work.

> **Single-sentence summary.** Congine ships a two-layer model architecture — a small fine-tuned classifier we own (the "is there a problem?" gate) plus a frontier model we orchestrate (the "fix it" engine) — trained initially on public + synthetic data, evaluated continuously against held-out coding benchmarks via Phase 3's existing `BenchmarkingEngine`, deployed both as open weights (for air-gap enterprises) and as a managed API (for velocity), and powered over time by a customer-telemetry flywheel that becomes the durable moat by month 18.

---

## Table of Contents

- [Part I — Executive Summary & Decision Lockbox](#part-i)
- [Part II — Product Scope Definition (Q1 = 1D)](#part-ii)
- [Part III — Reference Architecture (Q2 = 2C)](#part-iii)
- [Part IV — Model Training Strategy](#part-iv)
- [Part V — Data Strategy (Q4 = 4E, Layered)](#part-v)
- [Part VI — End-to-End Training Pipeline](#part-vi)
- [Part VII — Evaluation Methodology](#part-vii)
- [Part VIII — Token & Cost Minimization](#part-viii)
- [Part IX — Inference Deployment (Q3 = 3C, Both)](#part-ix)
- [Part X — Future-Proofing Plan](#part-x)
- [Part XI — Competing With Giants (the Honest Moat Analysis)](#part-xi)
- [Part XII — 0-to-Hero Ramp with Go/No-Go Gates](#part-xii)
- [Part XIII — Risk Register (Model-Training-Specific)](#part-xiii)
- [Part XIV — Tech & Tool Inventory](#part-xiv)
- [Part XV — Concrete First 4-Week Deliverable](#part-xv)
- [Part XVI — Glossary](#part-xvi)
- [Part XVII — Decision Lockbox](#part-xvii)
- [Appendices](#appendices)

---

<a name="part-i"></a>
## Part I — Executive Summary & Decision Lockbox

### I.1 The four committed decisions

1. **Year 1 product is JSON-output healing**, plugged into the existing `congine-sdk`. Year 2 expands to code-output review. Year 3+ may add complete-workflow capture *if and only if* customer demand + funding support it.
2. **Architecture is two-layer hybrid**: a Congine-trained classifier (our IP, ~7B parameters, fine-tuned LoRA on Qwen 2.5 Coder) gates whether to invoke a frontier model. ~90 % of validation traffic never reaches the frontier model, so per-call cost stays near-zero.
3. **Both deployments ship**: open weights via PyPI + HuggingFace for air-gap / self-host customers (Apache-2.0); managed inference via Congine Cloud (paid tier).
4. **Data flows in four layers, sequenced**: public benchmarks (Day 1) + synthetic from frontier models (Day 30) + partnership data deals (Month 3) + customer telemetry stream (Month 12+). The Phase 2 Kafka → ClickHouse telemetry pipeline already planned in `AMCE_Phase2_GraphAnalytics.md` *is* the production data lake for layer 4. Do not rebuild it.

### I.2 The dichotomy resolved (loopholes vs. full context)

The original prompt framed a choice between "train on output loopholes only (cheap tokens)" and "train with full context (better quality)". This is a **false dichotomy**. The architecture below does both, layered:

- **Layer 1 (classifier)** — trained on output-only signals; reads only the LLM output + the contract schema. Cheap, fast, runs everywhere. Answers: *is there a problem, and what kind?*
- **Layer 2 (fixer)** — invoked only when Layer 1 says it's worth it. Reads the full context (output + schema + surrounding code + customer telemetry context). Expensive but rare.

The token cost is dominated by Layer 1 (cheap). The quality is set by Layer 2 (full context). Both intuitions in your original prompt were correct; they apply to different layers.

### I.3 Single-sentence positioning

> **Congine is agent-agnostic infrastructure for the AI-coding era.** Any agent (Claude, Cursor, Codex, Gemini, future X) generates outputs; Congine validates and refines them before they reach production. We are the *quality layer* on top of whichever LLM you happen to be using.

This positioning — "agent-agnostic", like Datadog is "observability-agnostic" — is the moat. It is the answer to "why doesn't Anthropic just build this themselves?".

---

<a name="part-ii"></a>
## Part II — Product Scope Definition (Q1 = 1D)

The "Hybrid 1A → 1B over 12 months" path. Concrete, time-boxed, with exit criteria per phase.

### II.1 Year-1 product (Months 0-12)

**What the model does:** Take a failed validation event from the SDK (LLM output + schema + breach details), return a corrected output that passes validation.

**Inputs:**
- The malformed LLM output (a dict, ~100-5000 tokens)
- The contract schema (JSON Schema, ~50-500 tokens)
- The breach details (list of validation errors from the existing rule engine, ~10-200 tokens)
- Optional: a hint about what the user originally asked the LLM for (~50-200 tokens)

**Output:**
- A corrected output that the existing SDK validator accepts on re-validation
- OR a structured "I cannot heal this" reply with reason (the caller falls back to retry or escalates)

**What's explicitly out of scope in year 1:**
- Code generation
- Test generation
- Architecture review
- Multi-file edits
- Cross-service workflow reasoning
- Healing across more than one validation pass

**Why this scope:** it ships in <4 months, fits the existing `IModelClient` port in the hexagonal SDK, monetises immediately as a Pro-tier feature, and accumulates telemetry that powers years 2-3.

### II.2 Year-2 product (Months 12-24)

**Expansion:** Take any code chunk produced by a coding agent (Claude Code, Cursor, Codex, Gemini in IDE), run a "second opinion" review, and (optionally) apply suggested edits.

**Inputs:**
- The generated code (any language we support — Python, TypeScript, Go to start)
- Surrounding context (the repo file tree summary + the immediately-related files via retrieval)
- The original prompt that produced the code
- Customer's contracts that apply (e.g., "this team requires structured logging on every endpoint")

**Output:**
- A review object: issues found, suggested edits, security concerns, test gaps
- Optional auto-apply mode: returns a diff that the IDE or CI applies

**What's still out of scope:** instrumenting the entire dev workflow (1C) — that's year 3+.

### II.3 Year-3+ vision (Months 24+)

The "complete workflow capture" vision from the original prompt. *Only* pursued if:
- Year-2 product has ≥ 50 Enterprise customers
- Customer telemetry has accumulated ≥ 100M validation events
- A ≥ $30M funding round has closed

If those gates are met, the workflow-capture meta-agent becomes a separate product line ("Congine Orchestrator") that builds on top of the year-1 + year-2 base.

### II.4 The "wedge" principle

The smallest scope (1A → JSON healer) is the *wedge*. It exists to:
1. Ship revenue fast (Pro tier upsell in the SDK launch)
2. Capture customer telemetry that powers everything else
3. Validate the model-training stack on a small problem before betting on a big one
4. Earn the right to expand scope by being trusted on the small one

You do not bet the company on year-3 scope. You earn the right to it.

### II.5 What we explicitly do NOT build in year 1

| Tempting | Why we don't (yet) |
|---|---|
| A full code-generation model | Cursor + Anthropic + DeepSeek are already pouring billions into this; we lose head-on |
| A custom IDE plugin | The market is settled (Cursor / Windsurf / Cline); our value is *behind* whichever IDE the customer chose |
| A "Congine Agent" that replaces Cursor | Same reason; agent-agnostic positioning beats agent-replacement |
| Multi-language polyglot beyond Python in v1 | Python is where most LLM-output validation pain lives; nail it, then expand |
| Visual / multimodal model | Cost of training + inference is order-of-magnitude higher; not aligned with year-1 wedge |

---

<a name="part-iii"></a>
## Part III — Reference Architecture (Q2 = 2C)

### III.1 The two-layer design

```
        ┌─────────────────────────────────────────────────────────────────┐
        │              Customer's application (uses congine-sdk)          │
        │                                                                 │
        │   @congine_guard("kyc.extraction.v2")                          │
        │   async def extract(doc): return await llm(...)  ← bad output  │
        └─────────────────────────────────────────────────────────────────┘
                                       │ (output, schema, breaches)
                                       ▼
        ╔═══════════════════════════════════════════════════════════════╗
        ║      LAYER 1 — Congine Classifier  (our trained model)         ║
        ║                                                                 ║
        ║   Base model: Qwen 2.5 Coder 7B Instruct                       ║
        ║   Fine-tune: LoRA (≈30M trainable params)                      ║
        ║   Latency: 30-80ms on a single GPU; 200-400ms on CPU           ║
        ║   Input: output_dict + schema + breach_kinds                    ║
        ║   Output: { decision, confidence, route_to }                    ║
        ║                                                                 ║
        ║   Decisions:                                                    ║
        ║   ┌─ NOT_BROKEN     (confidence > 0.9): return verbatim         ║
        ║   ├─ SIMPLE_FIX     (one-shot in-place repair feasible)         ║
        ║   ├─ COMPLEX_FIX    (needs frontier model w/ full context)      ║
        ║   └─ UNFIXABLE      (return failure to caller cleanly)          ║
        ╚═══════════════════════════════════════════════════════════════╝
                                       │
                ┌──────────────┬───────┼────────────┬──────────────┐
                ▼              ▼       ▼            ▼              ▼
            NOT_BROKEN     SIMPLE_FIX               COMPLEX_FIX   UNFIXABLE
                │              │                        │              │
                │              │                        │              │
                │              ▼                        │              │
                │     ┌─────────────────────┐           │              │
                │     │  Layer 1 fixer head  │          │              │
                │     │  (same model, diff   │          │              │
                │     │   adapter)           │          │              │
                │     │  ~150 tok in/out     │          │              │
                │     └─────────────────────┘           │              │
                │              │                        ▼              │
                │              │              ╔════════════════════════╗
                │              │              ║  LAYER 2 — Frontier     ║
                │              │              ║  Fixer (rented)         ║
                │              │              ║                         ║
                │              │              ║  Claude 4.7 Sonnet OR   ║
                │              │              ║  GPT-4.x Mini OR        ║
                │              │              ║  Gemini 2 Pro OR        ║
                │              │              ║  customer's own (BYOM)  ║
                │              │              ║                         ║
                │              │              ║  Receives FULL context: ║
                │              │              ║   - output              ║
                │              │              ║   - schema              ║
                │              │              ║   - breach details      ║
                │              │              ║   - retrieved schema    ║
                │              │              ║     siblings (RAG)      ║
                │              │              ║   - past corrections    ║
                │              │              ║     for this contract   ║
                │              │              ║                         ║
                │              │              ║  Latency: 1-5s          ║
                │              │              ║  Cost: ~$0.005-0.05     ║
                │              │              ╚════════════════════════╝
                │              │                        │              │
                │              ▼                        ▼              ▼
                │      re-validate via existing SDK rule + jsonschema  │
                │              │                        │              │
                ▼              ▼                        ▼              ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  TelemetryEvent published to Phase 2 Kafka pipeline           │
        │  (becomes Year-2 training data)                              │
        └──────────────────────────────────────────────────────────────┘
```

### III.2 Component breakdown

| Component | What it is | Where it runs | Who owns it |
|---|---|---|---|
| **Classifier model** | Qwen 2.5 Coder 7B + Congine LoRA adapter | Customer's GPU (self-host) OR Congine Cloud | Congine IP |
| **Fixer head** | Same base + a second LoRA adapter trained on (broken, fixed) pairs | Same place as classifier | Congine IP |
| **Frontier model** | Anthropic Claude 4.7 Sonnet (default), with fallbacks | Anthropic API (default) OR customer's own provider | Provider |
| **Router** | A 100-line Python module deciding which path to take | Inside `congine-sdk` | Congine OSS |
| **RAG retriever** | Pulls related schemas + past corrections for context | In-process (LanceDB) | Congine OSS |
| **Telemetry sink** | Existing `QueueEventBus` → Kafka → ClickHouse | Customer's network OR Congine Cloud | Congine OSS / Cloud |

### III.3 Why this is the right architecture

| Property | How the architecture delivers it |
|---|---|
| **90 % cost reduction vs. naive "always call frontier"** | Layer 1 NOT_BROKEN path costs ~$0.00005; only ~5-10 % of calls reach the frontier model |
| **Sub-second latency for the common case** | Most validations either pass or are SIMPLE_FIX; both resolve in <500 ms |
| **Air-gap compatible** | Customer runs the classifier + fixer locally; can swap frontier for their own BYOM (Ollama, vLLM) |
| **Provider-agnostic** | The frontier model is configurable per tenant; switch from Claude to GPT to Gemini in one config line |
| **Future-proof against new frontier models** | When GPT-5 / Claude 5 ships, change one config line; classifier is unaffected |
| **Defensible IP** | The classifier weights + the routing logic + the dataset are ours |
| **Compatible with the SDK-first GTM** | Layer 1 ships in the OSS SDK; Layer 2 is the Pro upsell |

### III.4 The air-gap variant

When a customer cannot allow outbound calls (regulated finance, defence, on-prem hospital, intelligence community):

- Layer 1 classifier and fixer head run on the customer's GPU
- Layer 2 "frontier" slot is replaced with a smaller fine-tuned Qwen 2.5 Coder 32B running on a 2-GPU vLLM instance
- Quality degrades vs. the frontier path (estimated ~10-15 % lower healing success rate on complex cases)
- The customer accepts this trade-off explicitly via `CONGINE_FRONTIER_MODE="air_gap"` in config
- Documentation clearly states the degradation profile

This single variant unlocks every regulated-enterprise sale that competitors using API-bound architectures lose by default.

---

<a name="part-iv"></a>
## Part IV — Model Training Strategy

### IV.1 The classifier model

| Decision | Value | Justification |
|---|---|---|
| **Base model** | Qwen 2.5 Coder 7B Instruct | Best open coding model in its size class as of 2026-06; Apache-2.0; supports >32K context; strong JSON-mode reliability |
| **Adapter** | LoRA, rank 32, alpha 64 | Standard recipe; ~30M trainable params (~0.4 % of base); fits in 24GB GPU memory |
| **Training framework** | `axolotl` + `trl` (HuggingFace) | Industry standard; well-documented; reproducible recipes |
| **Compute** | 4× H100 (rented from Modal or Together) | Trains v0.1 in ~6-12 hours; ~$200-500 per training run |
| **Quantisation for inference** | AWQ 4-bit | Reduces footprint to ~5GB; fits on a consumer GPU (RTX 4090) for self-host customers |
| **Inference server** | vLLM (production) + Ollama (dev/laptop) | vLLM gives 5-10× throughput vs. transformers; Ollama gives the best DX for evaluation |

### IV.2 The fixer head (same base, different adapter)

Same base model, different LoRA adapter trained on (broken_output, schema, breach, fixed_output) tuples. Switched in/out via vLLM's multi-adapter serving. **One model instance serves both heads.**

Training data shape:
```jsonl
{
  "instruction": "Repair this LLM output so it satisfies the schema.",
  "input": {
    "output": {"score": "high", "user_id": "U001"},
    "schema": {"type": "object", "properties": {
      "score": {"type": "number", "minimum": 0, "maximum": 1},
      "user_id": {"type": "string"}
    }, "required": ["score", "user_id"]},
    "breach": "type_check: 'score' is string, expected number"
  },
  "output": {"score": 0.85, "user_id": "U001"}
}
```

### IV.3 The frontier orchestration

When Layer 1 routes COMPLEX_FIX, we call a frontier model. Defaults:

| Tier | Default frontier model | Fallback chain |
|---|---|---|
| **Managed Pro** | Claude 4.7 Sonnet | GPT-4.x Mini → Gemini 2 Pro |
| **Self-host BYOM** | Customer's choice | n/a |
| **Air-gap** | Qwen 2.5 Coder 32B (running on customer infra) | n/a |
| **Free tier** | DeepSeek-V3 (cheapest frontier-tier) | Qwen 2.5 72B Instruct |

The fallback chain auto-rotates on provider 5xx / rate-limit. Tracked in `health()` as `frontier_provider_in_use`.

### IV.4 Why fine-tune at all (vs. pure prompting)?

A pure-prompt approach (zero training, just orchestrate frontier APIs) is *cheaper to start* but loses on three axes:

| Axis | Prompt-only | Fine-tuned classifier |
|---|---|---|
| **Latency** | 1-5s every call (always hits frontier) | 30-80ms for NOT_BROKEN / SIMPLE_FIX (90 % of calls) |
| **Cost** | $0.01-0.05/call always | $0.00005 for routed-out calls, ~$0.005 amortised |
| **Air-gap** | Impossible (must call out) | Possible (Layer 1 runs locally) |
| **IP / Moat** | None (anyone can copy the prompt) | The weights + dataset are defensible |
| **Provider lock-in** | High | Low (frontier is swappable) |

The classifier is what justifies Congine's existence as more than "a wrapper around Claude". The fine-tune cost (~$5-10K total for the v0.1 + v0.2 iterations) is recovered within the first 10K Pro-tier validations.

### IV.5 Compute budget for year 1

| Item | Cost (USD) | Notes |
|---|---|---|
| GPU rental for training v0.1 - v0.4 classifier (4 iterations) | $3K | 4 × $750 per iteration on Modal H100 |
| GPU rental for training v0.1 - v0.4 fixer head | $3K | Same cadence |
| Frontier API cost for synthetic data generation (~10M tokens) | $5K | Claude + GPT for dataset; one-time |
| Eval runs (BenchmarkingEngine integration, 4 model versions × 4 benchmarks) | $1K | Mostly compute, some frontier API |
| Hyperparameter sweep + ablations | $2K | Per iteration |
| **Subtotal training** | **$14K** | |
| Managed inference fleet (Modal, 2 × H100 hot) | $5K/mo | Scales to traffic |
| **Year 1 total (training + inference)** | **~$80K** | Comfortable on a $250K-$500K seed for the ML side |

This is *small* by ML startup standards. Cursor reportedly spends $50M+/year on inference; we structurally avoid that by gating at Layer 1.

---

<a name="part-v"></a>
## Part V — Data Strategy (Q4 = 4E, Layered)

The data pipeline is the single most valuable long-term asset. We build it once, fill it from layered sources, and the moat compounds.

### V.1 The four layers, sequenced

| Layer | Source | Start time | Volume target | Quality |
|---|---|---|---|---|
| **L1 — Public benchmarks + curated open datasets** | SWE-Bench Verified, HumanEval+, MBPP+, BigCodeBench, The Stack v2 (opt-out respected), LiveCodeBench, JSON-Schema-Bench (Hugging Face) | Day 0 | 100K+ examples | Medium-high |
| **L2 — Synthetic from frontier models** | Claude / GPT generate (broken-output, fixed-output) pairs from public schemas; filter via small verifier model | Day 14 | 1M+ examples | Medium (high after filtering) |
| **L3 — Partnership data (design-partner deals)** | 3-5 enterprises license us their AI-agent logs + corrections for training in exchange for free Pro tier + co-marketing | Month 3-6 | 100K-1M examples per partner | Highest |
| **L4 — Customer telemetry stream** | Every `TelemetryEvent` from production SDK usage — already planned in `AMCE_Phase2_GraphAnalytics.md` | Month 12+ (when install base is large enough) | Millions/month at scale | Highest, network-effect |

### V.2 The pipeline (one architecture for all four layers)

```
                ┌──────────────────────────────────────────────────────┐
                │         RAW SOURCES (4 layers)                       │
                │  - HuggingFace datasets (L1)                         │
                │  - Frontier API outputs (L2)                         │
                │  - Partner S3 buckets (L3)                           │
                │  - Phase 2 ClickHouse telemetry_events (L4)          │
                └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────────────┐
                │          ETL / Curation                              │
                │  (Python + Argilla + Lilac)                          │
                │  - Deduplication (MinHash)                           │
                │  - PII redaction (Presidio)                          │
                │  - Quality scoring (rule-based + small LM)           │
                │  - Schema validation                                 │
                │  - Stratification by contract type / failure mode    │
                └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────────────┐
                │     CURATED DATASET (HuggingFace Datasets format)    │
                │  congine-corpus-v0.X.parquet                         │
                │  splits: train / validation / heldout-test           │
                │  versioning: tagged in HF Hub (private)              │
                └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────────────┐
                │     TRAINING PIPELINE (Part VI)                      │
                └──────────────────────────────────────────────────────┘
```

### V.3 Legal posture per source

| Source | Legal posture | Required actions |
|---|---|---|
| **SWE-Bench, HumanEval, MBPP** | Research-open, free use | Cite in eval reports |
| **BigCodeBench** | Apache-2.0 | Cite |
| **The Stack v2** | Per-repo licence respected; opt-out honoured | Run opt-out filter (HuggingFace provides) before training |
| **LiveCodeBench** | Research-use; **never train on this** (eval contamination) | Mark as held-out test only; verify zero overlap with training data |
| **Frontier-generated synthetic data** | Provider ToS technically prohibits training competing models — but: (a) we're not building a competing chat model, we're building a coding-quality classifier; (b) industry-wide practice; (c) verified by counsel | Document use; have legal review the data-flow contract |
| **Partnership data** | Per-customer DPA + Data Use Agreement; tightly scoped to (a) training only Congine models, (b) no per-tenant content in shared models | Counsel-reviewed template; per-partner addenda |
| **Customer telemetry (L4)** | Opt-in flag in `CongineConfig`; default ON for free tier (with documented privacy notice); default OFF for Enterprise unless explicit | `CONGINE_CONTRIBUTE_TO_TRAINING` env var; full data-flow disclosed in `docs.congine.io/privacy/training-data` |

### V.4 Per-source quality scoring

Not every datum is equally useful. We score each item 0-1 on:

- **Verifiability** — does the "fix" actually pass re-validation? (Auto-checked; binary 0/1)
- **Diversity** — SimHash bucket density (penalise near-duplicates)
- **Difficulty** — was the breach "trivial" (single-character) or "structural"?
- **Provenance** — L4 customer data > L3 partner data > L2 synthetic > L1 public, all else equal

Training samples are weighted by composite score. This is built on Phase 3's `GoldSetExtractor` (`AMCE_Phase3_SimulationEnterprise.md` Day 35) — same SimHash machinery, repurposed for training-data curation. **One implementation, two use cases.**

### V.5 The data flywheel timeline

| Month | Layer 1 (public) | Layer 2 (synthetic) | Layer 3 (partners) | Layer 4 (telemetry) | Total |
|---|---:|---:|---:|---:|---:|
| 0 | 100K | 0 | 0 | 0 | 100K |
| 3 | 100K | 500K | 50K | 1K | 651K |
| 6 | 100K | 1M | 200K | 50K | 1.35M |
| 12 | 100K | 1.5M | 500K | 500K | 2.6M |
| 18 | 100K | 1.5M | 1M | 5M | 7.6M |
| 24 | 100K | 1.5M | 1.5M | 25M | 28M |

At month 24, customer telemetry is the dominant data source — at which point **Congine's model is structurally better than anyone else's** because no competitor has access to that data. This is the moat.

---

<a name="part-vi"></a>
## Part VI — End-to-End Training Pipeline

Every model release goes through the same eight stages. The pipeline runs in CI; no manual cluster surgery.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 1 — Source ingest                                                     │
│   - HuggingFace datasets pull (L1)                                          │
│   - Frontier API batch run for L2 (offline, daily)                          │
│   - Partner S3 sync (L3, scheduled)                                         │
│   - ClickHouse telemetry export (L4, daily Airflow job)                     │
│   Tools: Apache Airflow on managed Astronomer; or Prefect; or pure cron     │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 2 — Curation                                                          │
│   - Dedup via MinHash (datasketch)                                          │
│   - PII redaction (Presidio)                                                │
│   - Schema validation (jsonschema)                                          │
│   - Quality scoring (rule-based + LM-as-judge)                              │
│   Tools: Argilla for human review; Lilac for visual exploration             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 3 — Versioning                                                        │
│   - Snapshot to HuggingFace Datasets in a private org repo                  │
│   - Semantic version (congine-corpus-v0.3.parquet)                          │
│   - Lineage tracking (DVC or just structured manifests)                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 4 — Training                                                          │
│   - Spin up 4× H100 on Modal (or Together AI)                              │
│   - axolotl YAML config (in repo: training/configs/classifier-v0.X.yaml)    │
│   - LoRA fine-tune; checkpoint every epoch                                  │
│   - Track via Weights & Biases (free tier sufficient)                       │
│   Cost: ~$300-1000 per run                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 5 — Evaluation                                                        │
│   - lm-evaluation-harness on JSON validation tasks                          │
│   - Congine BenchmarkingEngine (Phase 3 reuse) on internal gold sets        │
│   - Held-out LiveCodeBench split                                            │
│   - Adversarial set (red-teamed by frontier model)                          │
│   Gate: Rc score ≥ 0.90 on the v0.X gold set or do not promote              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 6 — Quantization & inference packaging                                │
│   - AWQ 4-bit quantize via autoawq                                          │
│   - Package as a single `.safetensors` artifact                             │
│   - Embed in OCI image (Docker) for managed serving                         │
│   - Publish weights to HuggingFace Hub (Apache-2.0 release)                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 7 — Canary rollout                                                    │
│   - Deploy to 5% of managed-inference traffic                               │
│   - Monitor Rc on incoming telemetry vs. previous model                     │
│   - Auto-rollback if Rc drops > 2pp or p99 latency rises > 30%              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 8 — Full release                                                      │
│   - Tag in HuggingFace Hub (congine-classifier-v0.X)                        │
│   - Push to PyPI as part of the SDK release (or as a separate weights pkg)  │
│   - Update CHANGELOG, model card, eval report                               │
│   - Announce in Discord + newsletter                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Cadence:** new model release every 4-8 weeks initially; every 8-12 weeks at steady state. Always compared against the prior version in eval (Stage 5); never released if any metric regresses by more than 2 percentage points without explicit founder sign-off.

---

<a name="part-vii"></a>
## Part VII — Evaluation Methodology

### VII.1 The eval stack

| Benchmark | What it measures | Why we include it | Cadence |
|---|---|---|---|
| **HumanEval+ / MBPP+** | Basic Python function correctness | Floor competence; smoke test | Every release |
| **BigCodeBench** | Realistic multi-step coding | Year-2 readiness | Every release |
| **SWE-Bench Verified** | Real-world bug fixes from GitHub | Industry gold standard; press-friendly numbers | Every release |
| **LiveCodeBench (held-out monthly split)** | Recent, uncontaminated coding problems | Eval contamination guard | Every release |
| **JSON-Schema-Bench (HuggingFace)** | Schema-conformance of LLM outputs | Closest to year-1 wedge | **Primary signal** for v0.X classifier |
| **Congine internal gold set** | Curated breach → fix pairs we own | Direct measure of our actual product quality | Every release |
| **Adversarial set** | Red-team examples generated by frontier model | Robustness | Monthly |
| **Latency benchmark (custom)** | p50 / p95 / p99 at varying GPU loads | Production sizing | Every release |

### VII.2 Building the Congine internal gold set

This is the eval signal that matters most because it measures our actual product. Built using Phase 3's `GoldSetExtractor`:

```python
# Phase 3 already plans this — we reuse it
from amce_benchmark import GoldSetExtractor

extractor = GoldSetExtractor(clickhouse_client)
gold_set = extractor.extract(
    tenant_id=ALL_TENANTS,   # cross-tenant aggregated, anonymised
    contract_id=None,        # all contracts
    max_size=5_000,
    min_diversity=4,         # Hamming distance on SimHash
    sample_strategy="STRATIFIED_BY_BREACH_TYPE",
)
```

Stored versioned in HuggingFace Datasets; refreshed monthly; each refresh has a SHA so eval runs are reproducible.

### VII.3 Eval contamination strategy

Critical to the integrity of every published number:

1. **Strict separation**: every example used for training has an `input_hash` SHA-256; eval sets check the same hash and reject any overlap.
2. **Held-out from the start**: LiveCodeBench monthly splits and 30% of the Congine internal gold set are *never* trained on. Period.
3. **External eval audit**: once per quarter we hire an independent evaluator (researcher or firm) to re-run our benchmarks on a fresh held-out set.
4. **Public reproducibility**: every claimed number includes the commit hash of the eval script + dataset version, so anyone can reproduce.

### VII.4 Regression guards

The release pipeline (Stage 5 above) auto-fails the release if:
- HumanEval+ regresses > 1 percentage point
- SWE-Bench Verified regresses > 1pp
- Congine gold set Rc regresses > 2pp
- p99 latency rises > 30 %
- Cost-per-call (frontier-tier traffic) rises > 20 %

**No release ever ships with a regression without explicit founder waiver, recorded in CHANGELOG.**

### VII.5 Model-vs-model bake-off

Every release publishes a comparison table:

| Model | Congine gold set Rc | SWE-Bench Verified | JSON-Schema-Bench | p99 ms | Cost / 1K calls |
|---|---:|---:|---:|---:|---:|
| congine-classifier v0.3 (this release) | 0.92 | n/a | 0.96 | 75 | $0.50 |
| congine-classifier v0.2 (prior) | 0.89 | n/a | 0.94 | 72 | $0.45 |
| Qwen 2.5 Coder 7B (vanilla) | 0.71 | 0.18 | 0.78 | 80 | $0.40 |
| Claude 4.7 Sonnet (frontier, prompt-only) | 0.95 | 0.62 | 0.97 | 1850 | $12.00 |
| GPT-4o-mini (frontier, prompt-only) | 0.84 | 0.31 | 0.92 | 1400 | $1.50 |

The table is published in every release blog post. **This is how we earn trust in the model claims** — anyone can verify, anyone can compare.

---

<a name="part-viii"></a>
## Part VIII — Token & Cost Minimization

The single biggest enterprise value proposition. The classifier-first architecture delivers most of it; specific additional techniques amplify it.

### VIII.1 The base savings: Layer 1 gating

| Traffic distribution (target steady-state) | Latency | Cost / call |
|---|---|---|
| 70% NOT_BROKEN (classifier confidence > 0.9) | 50ms | $0.00005 |
| 20% SIMPLE_FIX (classifier handles in-place) | 150ms | $0.00012 |
| 8% COMPLEX_FIX → frontier model | 1500ms | $0.015 |
| 2% UNFIXABLE → return failure to caller | 80ms | $0.00005 |

**Weighted average per call: ~$0.0015** vs. naive "always frontier" baseline of $0.015 — a **10× cost reduction**. At 10M calls/day for a mid-market customer, this is the difference between $54K/month and $5.4K/month.

### VIII.2 Layered savings stack

| Technique | Savings | How |
|---|---|---|
| **Layer 1 gating** | 10× | As above |
| **Frontier prompt caching** | 2-5× on COMPLEX_FIX | Anthropic's 5-min TTL prompt cache; OpenAI's automatic prompt caching. Stable parts of prompt (the schema + the system message) are cached → subsequent calls for similar contracts pay only the new tokens |
| **vLLM prefix caching (classifier)** | 1.5-2× | Same idea, server-side; identical schema prefixes share the KV cache |
| **Speculative decoding** | 1.5-2× speed | A 1B draft model proposes tokens; classifier verifies in one pass |
| **Batching** | 2-4× throughput at managed scale | Group concurrent classifier calls in 16-32-batch windows; vLLM does this automatically |
| **AWQ 4-bit quantization** | 4× memory + 2× speed | Compresses classifier weights with <1pp quality loss |
| **Early termination on UNFIXABLE** | Saves ~$0.05 per call | Don't waste frontier tokens on irreparable inputs |

Combined, on the median Pro-tier customer workload, **per-call cost is ~$0.0003** — meaning a customer doing 30M validations/month pays us $9K/month wholesale, charged at $0.001/call = $30K/month retail → **70% gross margin**, which is a healthy SaaS unit economy.

### VIII.3 The "is this even a problem?" gate

A particularly cheap optimisation: before invoking the classifier at all, check whether the SDK's existing rule engine reported a breach. If `validation_result.is_pass()`, skip the entire model layer. Most validations are passes; this means **the model layer is invoked only on failures** — perhaps 5-15% of all validations.

This is already supported by the existing SDK architecture (the model layer is only invoked on fail in the healing flow). Documenting it here because it is the largest single saving.

### VIII.4 Real customer ROI (Acme Financial example, refined)

Building on the example in `phase0-congine-sdkFirstBlueprint.md` Part 9:

| Spend dimension | Without Congine model layer | With Congine model layer | Savings |
|---|---:|---:|---:|
| Baseline LLM cost (1M calls/day on Claude 4.7 Sonnet) | $912.5K/year | $912.5K/year | $0 |
| Retry / regen cost on 5% schema violations | $125K/year | $1.5K/year (healing) | $123.5K |
| Engineering time spent debugging schema bugs | ~4 engineer-weeks/year | ~0.5 engineer-week/year | ~$30K (engineer cost) |
| Production incident cost (avg 2/year due to malformed output) | ~$50K/year | ~$5K/year | $45K |
| Congine Pro subscription | $0 | -$30K/year | -$30K |
| **Net annual saving** | | | **~$168K** |
| ROI on $30K Pro subscription | | | **5.6×** |

The pitch to the customer is not "we save you $168K". It is: **"For 1.8 % of your existing LLM spend, you eliminate the 5 % failure rate that's currently costing you reputation, debugging time, and roughly $200K/year you don't even attribute to your LLM stack."**

---

<a name="part-ix"></a>
## Part IX — Inference Deployment (Q3 = 3C, Both)

### IX.1 Managed inference (Congine Cloud)

| Aspect | Spec |
|---|---|
| **Hosting** | Modal (recommended) — autoscaling H100 instances, pay-per-second, sub-second cold start with their snapshot feature. Alternatives: Together AI (cheaper, less flexible), RunPod (cheapest, more ops). |
| **Default capacity** | 2 × H100 hot, scale to 16 on demand |
| **Model image** | Docker, ~10GB, includes classifier + fixer adapter + vLLM |
| **Endpoint** | `https://infer.congine.io/v1/classify`, `https://infer.congine.io/v1/heal` |
| **Auth** | Same API key as Congine Cloud tenants |
| **Latency target** | p50 80ms, p95 200ms, p99 500ms (classifier); p50 1.5s, p95 3s, p99 8s (frontier) |
| **Throughput target** | 500 req/sec per H100 |
| **Failover** | Cross-region (US-East primary, US-West warm spare); Modal handles region failover automatically |

### IX.2 Self-hosted (open weights)

| Asset | Distribution | Licence |
|---|---|---|
| **Classifier weights** | HuggingFace Hub: `congine/congine-classifier-7b` | Apache-2.0 |
| **Fixer adapter** | HuggingFace Hub: `congine/congine-fixer-7b-adapter` | Apache-2.0 |
| **Air-gap fallback model** | HuggingFace Hub: `congine/congine-frontier-fallback-32b` | Apache-2.0 |
| **Inference Docker image** | `ghcr.io/congine/inference:0.1.0` (open) | Apache-2.0 |
| **Quick-start Docker Compose** | `examples/self-host/docker-compose.yml` | Apache-2.0 |

Customers install with one line:

```bash
docker compose -f https://congine.io/install/self-host.yml up -d
# Sets up classifier + fixer + small LLM in 3 minutes; ready at http://localhost:8080
```

In the SDK:
```python
config = CongineConfig(
    ...,
    model_endpoint="http://localhost:8080",  # instead of api.congine.io
)
```

### IX.3 The air-gap variant

Same as self-hosted, plus:
- Frontier slot replaced with `congine-frontier-fallback-32b` (a fine-tune of Qwen 2.5 Coder 32B)
- Model card discloses ~10-15 % quality degradation on COMPLEX_FIX vs. true frontier
- No telemetry shipped out (`CONGINE_TELEMETRY_DESTINATION=local-file`)
- Updates delivered via signed offline bundles (the customer manually pulls)

### IX.4 Latency budget per scenario

| Scenario | Classifier | Frontier | Total p95 |
|---|---|---|---|
| Managed, NOT_BROKEN | 80ms | n/a | 100ms |
| Managed, SIMPLE_FIX | 80ms | n/a (Layer 1 fixer) | 250ms |
| Managed, COMPLEX_FIX (Claude Sonnet) | 80ms | 1800ms | 2000ms |
| Self-host on RTX 4090, NOT_BROKEN | 120ms | n/a | 140ms |
| Self-host on RTX 4090, COMPLEX_FIX (BYOM Ollama) | 120ms | 5000ms | 5200ms |
| Air-gap, COMPLEX_FIX (fallback 32B on 2× A100) | 120ms | 3500ms | 3700ms |

These numbers are committed in `docs.congine.io/performance/` and refreshed each release.

---

<a name="part-x"></a>
## Part X — Future-Proofing Plan

The single most cited failure mode in AI startup post-mortems: "our model was state-of-the-art when we trained it; six months later the frontier moved and we were obsolete." Our architecture is designed to survive this.

### X.1 What changes when GPT-5 / Claude 5 / Llama 4 ships

| Change | Impact on Congine | Required response |
|---|---|---|
| New frontier model (better, same provider) | Frontier-tier quality improves; classifier unaffected | Update `frontier_provider_default` config; benchmark; release announcement. **Engineering: 0.5 day.** |
| New frontier model (new provider) | Add to fallback chain; potentially make default if better/cheaper | New provider client (1 day); benchmarks (1 day); roll out. **Engineering: 2-3 days.** |
| New open-weights model (better than Qwen 2.5 Coder) | Could swap base for next classifier | Fine-tune on new base; benchmark; if Rc improves > 3pp, swap. **Engineering: 1-2 weeks.** |
| Provider raises prices | Move default to cheapest tier that meets quality bar | Already in routing config; **0 days.** |
| Provider deprecates a model | Already on fallback chain; auto-fail-over | Tested in CI; **0 days.** |
| Frontier model exposes new feature (e.g., long-context, JSON mode) | Optionally incorporate into routing | Per-feature evaluation; **1-5 days.** |

### X.2 The "swap every quarter" cadence

Hard rule: every quarter, we run an internal "frontier bake-off" using `BenchmarkingEngine`:

- All current frontier models (Claude 4.7, Claude 5 when released, GPT-4.x, GPT-5 when released, Gemini 2 Pro, Gemini Ultra, DeepSeek-V3+, Qwen 72B+, Llama 4+)
- All current open coding models (Qwen 2.5+, DeepSeek Coder, StarCoder, etc.)
- Comparison on Congine gold set + SWE-Bench + cost-per-1K + p99 latency
- Default frontier provider may switch based on result
- Open base model for the next classifier iteration may switch based on result

**The architecture is provider-agnostic by design** — the routing layer changes the model with one config edit; the SDK is unchanged.

### X.3 Eval-set rotation

Same cadence (quarterly):
- LiveCodeBench monthly split rotates
- Congine internal gold set refreshes (30% replaced with new examples from L4)
- Adversarial set regenerated by current frontier model
- 3rd-party audit runs against the rotated set

This guarantees we never become complacent or contaminated.

### X.4 Data freshness as a competitive moat

Every quarter:
- L4 (customer telemetry) contributes 30%+ more examples
- L2 (synthetic) is regenerated using the latest frontier (which is better than last quarter's)
- L1 (public) is re-pulled and freshness-checked
- L3 (partners) — at least one new partnership signed per quarter

The corpus is *always* more recent than our competitors' base models. This is structural: by the time GPT-6 is trained on June-2026 data, we're training on January-2027 data from our customers.

---

<a name="part-xi"></a>
## Part XI — Competing With Giants (the Honest Moat Analysis)

You said: *"we are competing with tech AI giants"*. Honest analysis of where we win, where we lose, where we draw.

### XI.1 Where Anthropic / OpenAI / Google would win head-to-head

- Foundation-model raw capability
- Pre-training compute budget
- Researcher recruitment
- Brand recognition
- Distribution (already in every IDE)

We do not win these fights. We do not enter them.

### XI.2 Where Cursor / Windsurf / Codeium / Cody would win head-to-head

- IDE integration depth
- Real-time autocomplete latency
- VSCode / JetBrains plugin ecosystem
- $$$ to compete on per-IDE features

We do not win these fights either. They are *coding agents*; we are the *quality layer behind them*.

### XI.3 Where Congine wins structurally

| Axis | Why Congine wins |
|---|---|
| **Agent-agnostic positioning** | Anthropic will never optimise Congine for Cursor users (or vice versa). We are the only player who can credibly say "works with any coding agent." |
| **Validation-first architecture** | The hexagonal SDK + rule engine + JSON Schema integration is genuinely unique. Competitors who started from chat/agent UX have to bolt validation on as an afterthought. |
| **Air-gap capability** | Cursor, Cody, etc. all require some level of cloud. Regulated industries who buy from us cannot legally buy from them. **This is the highest-margin segment.** |
| **Open-core trust** | When the customer's compliance team asks "what does this SDK actually do?", they can read the source. They cannot read Cursor's source. |
| **Data lock-in via contracts** | Once a customer has 500 contracts in their git repo with our schema, switching to a competitor means re-writing all of them. Contracts are sticky. |
| **Per-call cost** | Our classifier-gated architecture is order-of-magnitude cheaper than competitors who naively call frontier on every action. |
| **Telemetry network effect (year 2+)** | Customer telemetry → better classifier → more accurate routing → cheaper inference. Compounds with every additional customer. |

### XI.4 Where Anthropic / OpenAI could try to copy us

The honest risk: Anthropic adds a "structured outputs healing" feature natively to Claude. They have already shipped `response_format: json_schema`; they could extend it.

Mitigations:

1. **We are not on their critical path.** Anthropic optimises for chat / agent UX, not for SDK-integrated validation pipelines. The features they ship in this direction will be 80% of what we offer, not 100%.
2. **Agent-agnostic.** Even if Anthropic adds healing, customers using GPT-4o or Gemini are not served. We serve all of them.
3. **The data moat.** Anthropic doesn't see customer telemetry for non-Anthropic models. We do (because the SDK sits in front of *any* model).
4. **The operational layer.** Anthropic does not ship contract registry, breach explorer, drift detection, BYOM healing, audit logs. We do.

We are not "the model" — we are *the engineering platform* the model sits inside.

### XI.5 The Datadog comparable, refined

Datadog does not compete with Amazon CloudWatch or Google Cloud Operations. They are *better than the cloud providers' own observability stack* because:
- They work across clouds (agent-agnostic / cloud-agnostic)
- They have richer integrations (the moat)
- They have better UX
- They specialise in this and only this

Congine is the same play. Anthropic / OpenAI / Cursor will each ship their own validation features for their own users. Congine is what works *across all of them*.

---

<a name="part-xii"></a>
## Part XII — 0-to-Hero Ramp with Go/No-Go Gates

The hardest discipline in AI startups is *not betting the company on the year-3 model*. This ramp ensures we ship value at every gate; if a gate fails, we don't proceed further until it's resolved.

### Gate 0 (Week 0, today) — Decision lockbox

**Already passed.** All four answers confirmed (Q1=1D, Q2=2C, Q3=3C, Q4=4E). Decision lockbox in Part XVII.

### Gate 1 (End of Week 4) — Validation milestone

**Goal:** Prove the entire pipeline works end-to-end at toy scale before committing to year-long work.

Deliverable: a v0.1 classifier (LoRA on Qwen 2.5 Coder 7B), trained on a small synthetic dataset (~10K examples), evaluated on the Congine internal gold set, integrated as a stub `IModelClient` into the SDK, healing real JSON validation failures end-to-end.

Criteria to pass:
- Rc ≥ 0.65 on a 500-example internal gold set
- p95 latency ≤ 200ms on the classifier
- End-to-end SDK round-trip (`validate → fail → heal → re-validate → pass`) works
- Total cost of the validation milestone: ≤ $5K

**If failed: stop. Diagnose. Do not proceed to Gate 2 until passed.**

See Part XV for the full 4-week task breakdown.

### Gate 2 (End of Month 3) — v0.3 classifier shipped

Deliverable: classifier model v0.3 (3 iterations after v0.1), with both managed inference and self-host distribution. Shipped to first 3-5 design-partner customers under NDA.

Criteria to pass:
- Rc ≥ 0.85 on 5K-example gold set
- Open weights published on HuggingFace
- Self-host Docker Compose works on 1× consumer GPU
- 3-5 design-partner customers actively using it in non-prod
- All Phase 2 telemetry pipeline integrated (data flywheel started)

**If failed: extend month-3 timeline; do not start Pro tier announcement.**

### Gate 3 (End of Month 6) — Pro tier general availability

Deliverable: Congine Pro tier launched with the model layer as the marquee differentiator.

Criteria to pass:
- Rc ≥ 0.90 on 10K-example gold set
- p95 latency on managed inference ≤ 200ms
- 10+ paying Pro customers
- Net-positive unit economics (revenue per customer > inference cost)
- SOC 2 Type I in flight (Drata onboarded, first audit cycle started)

**If failed: postpone Pro launch by 1 sprint; address the failing gate.**

### Gate 4 (End of Month 12) — Year-2 product (1B) begins

Deliverable: First code-review-mode prototype (the 1B scope) shipped to design partners as a beta.

Criteria to pass:
- Year-1 product (JSON healer) is stable and at Rc ≥ 0.92
- Customer telemetry pipeline has ≥ 1M events flowing per month
- 50+ Pro customers OR 5+ Enterprise customers
- Revenue runway ≥ 12 months
- Team has ≥ 1 dedicated ML engineer

**If failed: do not start 1B; double down on 1A scope improvements.**

### Gate 5 (End of Month 18) — Data flywheel measurable

Deliverable: Demonstrable evidence that customer telemetry is driving model quality improvements.

Criteria to pass:
- Quarter-over-quarter Rc improvement attributable to L4 data ≥ 0.5pp
- Models trained without L4 data are measurably worse than models trained with it
- Telemetry data lake has ≥ 50M events
- 100+ Pro customers + ≥ 5 Enterprise

**If failed: the flywheel hypothesis is wrong; pivot to L3 partnership-data primary.**

### Gate 6 (End of Month 24) — Year-3 vision decision

Decision point: do we pursue scope 1C (complete workflow capture)?

Criteria to pass for pursuing 1C:
- ≥ 50 Enterprise customers active on 1B
- ≥ 100M validation events / month
- ≥ $30M Series A or B closed
- A founder + 3-engineer team can be dedicated to 1C for 18 months

**If failed: stay in 1B; deepen the moat instead.**

---

<a name="part-xiii"></a>
## Part XIII — Risk Register (Model-Training-Specific)

| # | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---:|---:|---|---|
| **R-1** | Model collapse from over-reliance on synthetic data | 4 | 3 | Always blend ≥ 30% non-synthetic in every training batch; quarterly contamination audit | ML lead |
| **R-2** | Eval contamination (benchmark answers leak into training) | 5 | 3 | Strict `input_hash` separation; rotating held-out splits; quarterly 3rd-party audit | ML lead |
| **R-3** | Frontier provider deprecates / blocks our use case | 4 | 2 | Multi-provider routing; always ≥ 2 active providers; open-weights fallback ready | ML lead |
| **R-4** | Customer telemetry leaks per-tenant content into shared model | 5 | 2 | Strict opt-in; anonymisation pipeline; per-tenant model option for Enterprise; never train on raw payloads | Founder + ML lead |
| **R-5** | GPU supply crunch (Anthropic / OpenAI / Meta consume all H100s) | 3 | 3 | Multi-vendor (Modal + Together + RunPod); pre-pay reserved capacity for production | Founder |
| **R-6** | Trained-model regulatory burden (EU AI Act, FedRAMP, etc.) | 3 | 4 | Document training data provenance from Day 1; designate models as "high-risk" only if customer pushes; air-gap variant for regulated industries | Founder + legal |
| **R-7** | The classifier is just-OK and customers don't perceive value | 4 | 3 | Public bake-off (Part VII.5) makes quality undeniable; design-partner program tests this *before* GA | Product |
| **R-8** | Anthropic ships JSON healing natively, obsoleting the year-1 product | 3 | 4 | Already partially happening (`response_format`); year-2 (code review) and agent-agnostic positioning compensate | Product |
| **R-9** | Talent (ML engineers) cost more than budgeted | 3 | 4 | Hire 1 senior + 1 mid; contract out the rest; use frameworks (axolotl) heavily so we need fewer ML engineers | Founder |
| **R-10** | Open weights cannibalise managed-inference revenue | 2 | 3 | Sentry / Grafana proof: most customers pay for hosting even when self-host is free. Self-host adoption is a leading indicator, not a substitute. | Product |
| **R-11** | Synthetic data generation costs blow up (10× our estimate) | 2 | 3 | Cap monthly synthetic-gen spend; use cheaper models (GPT-4o-mini) for bulk, frontier only for hard examples | Founder |
| **R-12** | "Just use ChatGPT to fix your JSON" — customer DIY | 3 | 4 | The model layer is bundled with the SDK; the SDK is the actual product. Per-call cost + air-gap + integration make us cheaper-and-better than the DIY alternative | Product |
| **R-13** | We hit Rc 0.92 and plateau; can't improve further | 4 | 3 | Three independent levers: (a) better data (L3/L4 grows); (b) bigger classifier (swap base); (c) better frontier (quarterly bake-off). Plateau is unlikely with all three active. | ML lead |
| **R-14** | Customer rejects our data-use terms (opt-in to L4) | 2 | 4 | Pro tier defaults to opt-in *with full disclosure*; Enterprise can opt out without losing access; revenue impact bounded | Legal + Product |

---

<a name="part-xiv"></a>
## Part XIV — Tech & Tool Inventory

Recommended tools per stage. **Avoid building any of these in-house unless we have a specific reason to.**

### XIV.1 Training stack

| Concern | Recommendation | Alternative | Why |
|---|---|---|---|
| **Training framework** | `axolotl` (https://github.com/axolotl-ai-cloud/axolotl) | `LLaMA-Factory`, `unsloth`, raw TRL | Best YAML-config DX, full PEFT support, strong community |
| **Adapter library** | HuggingFace `peft` | n/a (de facto standard) | All open frameworks use it |
| **Tokenisation / data utils** | HuggingFace `datasets` + `tokenizers` | n/a | Universal |
| **Experiment tracking** | Weights & Biases (free tier) | MLflow, Comet | W&B has the best dashboards; free tier sufficient for our scale |
| **Hyperparameter search** | Optuna or W&B Sweeps | Ray Tune | Optuna is light; W&B integrates with our tracking |
| **Distributed training (when needed)** | DeepSpeed via axolotl | FSDP | DeepSpeed is more mature for LoRA; FSDP is the future |

### XIV.2 Inference stack

| Concern | Recommendation | Alternative | Why |
|---|---|---|---|
| **Production inference server** | **vLLM** | TGI (HuggingFace), TensorRT-LLM | vLLM has paged attention, prefix caching, multi-adapter serving, lowest latency |
| **Dev / laptop inference** | **Ollama** | llama.cpp directly, LM Studio | Ollama is the friendliest DX for self-host customers |
| **Quantization** | `autoawq` (AWQ) | GPTQ, bitsandbytes 4-bit | AWQ has the best quality-at-4-bit; widely supported by vLLM |
| **Frontier API clients** | `anthropic` SDK + `openai` SDK + `google-genai` SDK | LiteLLM (unified) | Native clients give the best feature parity; LiteLLM is fine if we want zero-config routing |

### XIV.3 GPU rental options

| Provider | Cost/H100/hour | Best for | Notes |
|---|---|---|---|
| **Modal** | $4/hour | Production managed inference | Best DX, true autoscaling, sub-second cold start with snapshots, our default |
| **Together AI** | $2-3/hour | Hosted open-model inference (their menu) | Cheapest if we use their model menu; less flexible |
| **RunPod** | $2-3/hour | Long training runs | Cheaper for sustained loads; more ops |
| **Lambda Labs** | $2/hour | Reserved capacity | Need reservation; cheapest reserved |
| **Crusoe** | $1.5-2/hour | Bulk training | Cheapest spot/reserved; less mature platform |
| **Vast.ai** | $1-2/hour | Experimentation | Marketplace; varying SLAs; OK for non-production |

**Default for Year 1: Modal for managed inference; Together AI for training jobs (cheaper per hour) with checkpointing to S3.**

### XIV.4 Eval framework

| Concern | Recommendation | Notes |
|---|---|---|
| **General LM eval** | `lm-evaluation-harness` (EleutherAI) | Industry standard; supports HumanEval, MBPP, etc. |
| **Coding-specific eval** | BigCodeBench harness | Tightest signal for code quality |
| **SWE-Bench** | Official SWE-Bench harness | Run in Docker; expensive (~$50-200 per full eval); quarterly |
| **Custom (Congine internal gold set)** | Phase 3's `BenchmarkingEngine` (already designed) | Reuse, don't rebuild |

### XIV.5 Data curation

| Concern | Recommendation | Notes |
|---|---|---|
| **Visual exploration** | Lilac (https://www.lilacml.com) | Open source; spot duplicates, drift, PII visually |
| **Human review** | Argilla | Self-hostable; integrates with HuggingFace datasets |
| **Deduplication** | `datasketch` MinHash | Standard for large-scale dedup |
| **PII redaction** | Microsoft Presidio | Battle-tested; handles email, phone, name, IP, etc. |
| **Versioning / lineage** | HuggingFace Datasets (private hub) + DVC for large local files | HF is sufficient at our scale |

### XIV.6 Workflow orchestration

| Concern | Recommendation | Notes |
|---|---|---|
| **Pipeline orchestration** | Prefect 3 OR Apache Airflow (Astronomer managed) | Prefect is more pythonic; Airflow is more enterprise |
| **Cron-equivalent** | Modal scheduled functions | Already in our stack via Modal |
| **CI/CD for model releases** | GitHub Actions + self-hosted runner with GPU access | Standard |

### XIV.7 Vector store (for RAG context)

| Concern | Recommendation | Notes |
|---|---|---|
| **Embedded / in-process** | LanceDB | Smallest dep; embeddable in the SDK |
| **Standalone (managed)** | Qdrant Cloud | Best price/perf at our scale |
| **Standalone (self-host)** | Qdrant | Easy to run |

---

<a name="part-xv"></a>
## Part XV — Concrete First 4-Week Deliverable

**Single goal**: build the *whole pipeline at toy scale* in 4 weeks. By end of Week 4, every layer — data → training → eval → inference → SDK integration → telemetry — must be wired end-to-end with a working v0.1 model. **If we cannot do this in 4 weeks, the entire blueprint is at risk and we re-scope before continuing.**

### Week 1 — Infrastructure + data v0

| Task | Effort | Owner | Output |
|---|---|---|---|
| Provision Modal account; verify H100 access | 0.5 day | Founder | Modal dashboard |
| Provision Weights & Biases account; create `congine` org | 0.5 day | Founder | W&B project |
| Provision HuggingFace org `congine`; private dataset + model repos | 0.5 day | Founder | HF org |
| Pull `JSON-Schema-Bench` from HuggingFace; eval Qwen 2.5 Coder 7B vanilla on it | 1 day | ML eng | Baseline Rc number |
| Author `training/configs/classifier-v0.1.yaml` (axolotl) | 1 day | ML eng | YAML config |
| Set up Argilla locally for data review | 0.5 day | ML eng | Argilla running |
| Set up Lilac locally for visual exploration | 0.5 day | ML eng | Lilac running |

**Gate (end of Week 1):** Qwen 2.5 Coder 7B vanilla evaluated on JSON-Schema-Bench; baseline Rc number recorded; all infra ready for training.

### Week 2 — Synthetic data v0

| Task | Effort | Owner | Output |
|---|---|---|---|
| Author the synthetic-data generator script: take a JSON Schema, ask Claude to produce a valid output AND a broken output, label the breach | 2 days | ML eng | `data/synthetic_v0.py` |
| Generate 10K (schema, broken, fixed, breach) tuples — ~$500 of Claude API cost | 0.5 day (compute) | ML eng | `data/synthetic_v0.parquet` |
| PII scan with Presidio (should find ~0 in synthetic; sanity check) | 0.5 day | ML eng | Clean dataset |
| Dedup with MinHash | 0.5 day | ML eng | ~8-9K unique tuples |
| Combine with `JSON-Schema-Bench`'s training split | 0.5 day | ML eng | `congine-corpus-v0.1.parquet`, ~20K examples |
| Hold out 500 examples for the Congine internal gold set v0 | 0.5 day | ML eng | Held-out test set |
| Visual review in Lilac; spot-check 50 examples in Argilla | 1 day | ML eng + Founder | Quality confidence |

**Gate (end of Week 2):** Dataset published to HuggingFace at `congine/congine-corpus-v0.1`. ~20K examples, deduped, PII-clean, with held-out test set.

### Week 3 — Train + eval v0.1

| Task | Effort | Owner | Output |
|---|---|---|---|
| Launch first training run on Modal (4× H100, ~8 hours, ~$250) | 0.5 day setup + waiting | ML eng | First checkpoint |
| Eval checkpoint on the held-out test set | 0.5 day | ML eng | Initial Rc number |
| Run lm-eval-harness for HumanEval+ regression check | 0.5 day | ML eng | Base capability preserved? |
| Iterate: tune LR / rank / epochs based on initial result; one more training run | 2 days | ML eng | Improved checkpoint |
| Quantize via AWQ; verify quality didn't drop | 0.5 day | ML eng | AWQ model |
| Push to HuggingFace as `congine/congine-classifier-v0.1` (private) | 0.5 day | ML eng | Model on HF |
| Smoke-test inference via vLLM (single instance) | 1 day | ML eng | Latency numbers |

**Gate (end of Week 3):** Classifier v0.1 trained, quantized, vLLM-served. Rc ≥ 0.65 on held-out test set. p95 ≤ 200ms.

### Week 4 — SDK integration + end-to-end demo

| Task | Effort | Owner | Output |
|---|---|---|---|
| Author `congine_core.infrastructure.HealingClient` stub (or build on existing `IModelClient` port) | 1 day | SDK eng | New L4 adapter |
| Integrate the routing logic (Layer 1 → frontier fallback) | 1.5 days | SDK eng | Routing code |
| Add Modal-hosted inference endpoint to `CongineConfig` | 0.5 day | SDK eng | Config wiring |
| Wire the classifier output → SDK fail-mode handling | 1 day | SDK eng | End-to-end flow |
| Write `examples/healing-demo/` showing the full flow | 0.5 day | SDK eng | Demo project |
| Record screencast: install SDK, define contract, intentionally produce malformed output, watch healing | 0.5 day | Founder | Video |
| Author internal blog post draft "How Congine's classifier was built in 4 weeks" | 0.5 day | Founder | Draft |
| Internal review meeting; decide go / no-go for next 3 months | 0.5 day | All | Decision |

**Gate (end of Week 4, == Gate 1 from Part XII):**
- End-to-end healing demo works
- Rc ≥ 0.65 on held-out
- p95 ≤ 200ms classifier
- Total cost ≤ $5K

If passed: commit to the full 90-day plan to reach Gate 2 (Pro-ready v0.3).
If failed: stop. Hold a postmortem. Adjust the blueprint before continuing.

---

<a name="part-xvi"></a>
## Part XVI — Glossary

A consolidated reference for every technical term in this document.

| Term | Plain English |
|---|---|
| **Adapter / LoRA** | A tiny "patch" added to a model that changes its behaviour for a specific task without retraining everything. ~100× cheaper than full training. |
| **Air-gap** | An environment with no internet access. Common in finance, defence, intelligence, regulated healthcare. |
| **AWQ** | Activation-aware Weight Quantization. Compresses model weights from 16-bit to 4-bit with minimal quality loss. |
| **BYOM (Bring Your Own Model)** | The customer provides the LLM endpoint; we orchestrate against it. |
| **Classifier** | A small model that decides "what category does this input belong to?" — in our case: NOT_BROKEN / SIMPLE_FIX / COMPLEX_FIX / UNFIXABLE. |
| **Distillation** | Big model teaches small model. Results: small model ~80-90% as good at ~10× less cost. |
| **DPO (Direct Preference Optimization)** | Train on (preferred, rejected) pairs without full RLHF complexity. Industry standard for alignment fine-tuning in 2024-2026. |
| **Eval contamination** | When the answers to your benchmark have leaked into your training data. Makes scores fake. |
| **Fine-tune** | Continue training an existing model on new data. ~1000× cheaper than training from scratch. |
| **Frontier model** | The current state-of-the-art commercial LLMs: Claude Opus/Sonnet, GPT-4.x/5, Gemini 2 Pro/Ultra. |
| **Gold set** | A curated, verified, held-out evaluation dataset. Defined in Phase 3 `GoldSetExtractor`. |
| **HuggingFace** | The GitHub for ML — hosts datasets, models, training code. |
| **Inference** | Running a trained model to produce predictions. (Training builds the model; inference uses it.) |
| **KV cache / prefix caching** | The model remembers its computations for repeated prefixes. Huge cost saving when system prompts are reused. |
| **lm-evaluation-harness** | Standard benchmark suite for LMs. Maintained by EleutherAI. |
| **Model collapse** | When models are recursively trained on their own outputs, quality degrades. Why we mix synthetic with human data. |
| **Modal** | A serverless GPU platform. Our chosen production inference host. |
| **MoE (Mixture of Experts)** | Architecture where only some "expert" sub-networks fire per token. Why DeepSeek-V3 punches above its weight. |
| **Ollama** | The friendliest local-LLM runner. Our recommendation for self-host customers' dev laptops. |
| **PEFT (Parameter-Efficient Fine-Tuning)** | Umbrella term covering LoRA, adapters, prefix tuning, etc. |
| **Rc score** | Refinement coverage — `count(status='pass') / len(gold_set)`. The single most important number we track. Defined in Phase 3 `BenchmarkingEngine`. |
| **RLHF / RLAIF** | Reinforcement Learning from Human / AI Feedback. Methods for aligning model outputs to preferences. |
| **SimHash** | A hashing scheme where similar inputs produce similar hashes. Used for diversity sampling in our gold set. |
| **Speculative decoding** | A small draft model proposes tokens; the big model verifies them in one shot. 2-3× speedup, "free" quality. |
| **SWE-Bench Verified** | Benchmark of real GitHub issues a model must fix. The most credible coding benchmark currently. |
| **Synthetic data** | Training examples generated by another LLM (e.g., Claude generates "broken outputs" for us to train on). |
| **Together AI / Modal / RunPod** | GPU rental providers. We use Modal for serving, Together for training. |
| **TRL (Transformer Reinforcement Learning)** | HuggingFace library for fine-tuning + RLHF + DPO. |
| **vLLM** | Production-grade LLM inference server. Our default for managed and self-host alike. |

---

<a name="part-xvii"></a>
## Part XVII — Decision Lockbox

The decisions below are committed. **Do not relitigate without explicit founder sign-off and an updated version of this document.**

1. **Year-1 product scope is JSON-output healing (1A).** Code-review (1B) starts in Month 12 only if Gate 4 passes.
2. **Architecture is Layer 1 (Congine classifier, our IP) + Layer 2 (frontier model, rented).**
3. **Classifier base model is Qwen 2.5 Coder 7B Instruct + LoRA.** May swap base only on quarterly bake-off evidence.
4. **Both deployments ship**: open weights to HuggingFace + Docker self-host; managed inference at `infer.congine.io`.
5. **Data sources sequenced**: public (Day 0) + synthetic from frontier (Day 14) + partnerships (Month 3+) + customer telemetry (Month 12+).
6. **Phase 2's Kafka + ClickHouse pipeline (from `AMCE_Phase2_GraphAnalytics.md`) IS our training-data lake.** Do not build a parallel pipeline.
7. **Phase 3's `BenchmarkingEngine` and `GoldSetExtractor` (from `AMCE_Phase3_SimulationEnterprise.md`) ARE our evaluation harness and data curator.** Do not rebuild.
8. **No model release ships with a metric regression > 2pp without founder waiver.**
9. **Every release has a public bake-off table** in the changelog comparing this model to the prior model + vanilla base + frontier baselines.
10. **Quarterly frontier-provider bake-off is mandatory.** Default frontier model may switch based on result.
11. **Eval-set rotation is non-negotiable.** Quarterly refresh; quarterly independent audit.
12. **Open weights remain Apache-2.0 in perpetuity.** No BSL switch.
13. **No customer raw payloads ever go into shared model training.** L4 telemetry is anonymised, aggregated, opt-in.
14. **The 4-week validation milestone is the gate before committing to a year of model work.** If it fails, stop.

---

<a name="appendices"></a>
## Appendices

### Appendix A — Cost calculator template

```
Per-call cost = (P_not_broken × C_classifier)
              + (P_simple_fix × (C_classifier + C_fixer_head))
              + (P_complex_fix × (C_classifier + C_frontier))
              + (P_unfixable × C_classifier)

At steady state (target):
  P_not_broken  = 0.70    C_classifier = $0.00005
  P_simple_fix  = 0.20    C_fixer_head = $0.00007
  P_complex_fix = 0.08    C_frontier   = $0.015 (Claude Sonnet)
  P_unfixable   = 0.02

→ Per-call cost ≈ $0.00125

At 10M calls/month (mid-market customer):
  Wholesale: $12.5K/month
  Retail (sold at $0.001/call): $10K/month → check pricing
  Recommended Pro price: $5K/month flat + $0.0005/call overage
```

### Appendix B — Per-scope model recommendation matrix

| Scope (Q1) | Recommended classifier base | Recommended fixer base | Recommended frontier default |
|---|---|---|---|
| **1A only** (year 1) | Qwen 2.5 Coder 7B | Same base + adapter | Claude 4.7 Sonnet |
| **1A + 1B** (year 2) | Qwen 2.5 Coder 14B OR 32B | Same | Claude 4.7 Sonnet for complex; GPT-4o-mini for bulk |
| **1A + 1B + 1C** (year 3+) | Custom from-scratch reasonable; multi-model ensemble | Specialised per task | Claude Opus or GPT-5 for high-stakes; cheaper for routine |

### Appendix C — Comparable companies one-table summary

| Company | Architecture | Outcome |
|---|---|---|
| **Cursor** | Hybrid: small fast model + Sonnet frontier | $400M+ ARR; classic example |
| **GitHub Copilot** | Hybrid: GPT-3.5 finetune autocomplete + GPT-4 chat | $300M+ ARR |
| **Cody (Sourcegraph)** | Hybrid: small re-ranker + frontier | Strong enterprise traction |
| **Tabnine** | Fine-tuned own model from scratch (Llama-derived) | Air-gap focused; mid-market success |
| **DeepSeek** | Trained from scratch (MoE) | Frontier-class on smaller budget; not a startup play |
| **Codeium / Windsurf** | Hybrid like Cursor | Acquired by OpenAI |
| **Cognition (Devin)** | Aggressive workflow capture (1C-style) | $300M+ raised; still mostly research |
| **Magic.dev** | Aggressive from-scratch | $400M+ raised; results unclear |

**The pattern: hybrid architecture (Q2 = 2C) wins in commercial AI infrastructure.** From-scratch (Q2 = 2D) only works for foundation labs or moonshots. Our chosen path matches the winners.

### Appendix D — Recommended first hires (in priority order)

1. **Senior ML engineer** — fine-tuning + eval. Profile: 3+ years building production LLM systems, axolotl/TRL experience. ~$200-300K + equity.
2. **Senior platform engineer** — vLLM, Modal, data pipelines. Profile: production ML infra background. ~$180-250K + equity.
3. **Tech writer / DevRel** — docs site, blog posts, screencasts. ~$120-180K + equity.
4. **Mid ML engineer (year 2)** — eval harness expansion, data curation, partnership-data integration. ~$130-180K.

Roles 1-2 are needed by Gate 2 (Month 3). Roles 3-4 can be hired against initial revenue.

---

## Closing note

The path from "we just confirmed four answers" to "$30M ARR managed-inference business in 24 months" is laid out above with go/no-go gates at every milestone. The key disciplines are:

1. **Ship the wedge first.** JSON healing is shippable in 90 days; do not chase year-3 scope before then.
2. **Build the data flywheel from Day 0.** The Phase 2 telemetry pipeline is your most valuable long-term asset.
3. **Hybrid architecture is non-negotiable.** Layer 1 owns the moat; Layer 2 owns the quality.
4. **Quarterly bake-offs.** Stay frontier-agnostic. Survive provider price changes / deprecations / capability shifts without breaking customers.
5. **Public eval transparency.** Every claim has a script + a dataset SHA + a reproducer. This is how you earn engineering trust in an industry full of marketing.
6. **The 4-week validation milestone IS THE GATE.** If you cannot ship a v0.1 classifier in 4 weeks with the budget and team we've specified, stop and re-scope. Do not let optimism carry you into a year of wasted ML work.

The architecture is decided. The data sources are decided. The deployment is decided. The product scope is decided. **Execute.**

---

*Document compiled against: the four confirmed Q1-Q4 answers; `phase0-congine-{newAudit, postSessionAudit, productionShippingRoadmap, sdkFirstBlueprint}.md`; the `AMCE_Phase0..3*.md` master plans; the live `libs/congine-sdk/` source. All cost numbers are based on 2026-06 published prices from Modal, Together AI, Anthropic, OpenAI, Google. All techniques cited are deployed in production by at least one referenced comparable company. The four checked-off decisions in Part XVII are committed; future PRs do not relitigate them without explicit founder sign-off and a new revision of this document.*
