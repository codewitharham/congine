# 02 — PROBLEM 1: TOKEN OPTIMIZATION

**Purpose:** Rebuild, from first principles, *why* LLMs consume tokens, what prompt caching really
is, and the four mechanisms by which Congine reduces token spend — with the honest ranking of which
mechanism matters most. Two themes throughout: (1) logical reasoning behind the problem, (2) the full
technical workflow and where it lives in the engine.

**Prerequisite reading:** `00_START_HERE.md` (especially Correction 1) and `01`.

---

## PART 1 — THE REASONING: WHY DO LLMs BURN TOKENS AT ALL?

### 1.1 The single root fact: LLM APIs are stateless

An LLM API call is a **pure function**. You hand it a prompt, it hands you a completion, and then it
forgets you existed. There is no session, no memory, no "it remembers what we discussed." The next
call is a total stranger meeting your text for the first time.

Anthropomorphically: imagine a brilliant consultant with *perfect reasoning* but *total amnesia between
meetings*. Every time you walk into their office, you must re-hand them the entire case file — every
prior email, every decision, every constraint — because they remember nothing from yesterday. They
read the whole file, give you a sharp answer, and forget it all the instant you leave. That amnesia is
not a bug you can patch. It is how the API is built. And re-handing the file every time is where your
money goes.

This is the deep answer to what you remembered from our lost chat — *"the LLM is given a different
prompt each time, that is why it rethinks each time."* Let's make it precise: it's not that the prompt
is *different* each time; it's that even when the prompt is *mostly the same*, the model has **no
memory of having processed it before**, so it re-processes all of it from scratch. The "rethinking" is
literal re-computation of the model's internal state over every token you send.

### 1.2 What a token is, and why you pay for input too

Text is split into **tokens** by a tokenizer (byte-pair encoding, BPE). A token is roughly ¾ of a
word on average — "validation" might be one token, "hexagonal" might be two. You are billed on tokens,
not characters or words.

Crucially, you pay for **both directions**:
- **Input tokens** = everything you *send*: system prompt + conversation history + injected context +
  the current request. In agentic coding, this is *by far* the larger number.
- **Output tokens** = what the model *generates*. Usually smaller, but priced higher per token.

The naive mental model ("I only pay for the answer") is wrong and expensive. You pay for the *whole
case file* on every visit, and the case file grows as the conversation grows.

### 1.3 Why re-sending is computationally expensive (the prefill phase)

To understand caching later, you need to know what the model *does* with your input. A transformer
processes a prompt in two phases:

- **Prefill:** the model reads the entire input prompt and builds an internal representation of it.
  For every layer of the network and every token, it computes three vectors — a **Query (Q)**, a
  **Key (K)**, and a **Value (V)** — and each token *attends* to all previous tokens using these.
  This is the compute-heavy phase, and it scales badly with length: attention is roughly O(N²) in the
  number of tokens N (each token looks at every earlier token).
- **Decode:** the model generates the completion one token at a time, each new token attending back
  over the prefilled context.

Here is the key structure to lock in: the **K and V vectors for a given token depend only on that
token and the tokens *before* it** (attention is causal — the future can't affect the past). So for a
*fixed prefix* of the prompt, the K and V vectors are **deterministic and identical every time**.
Together, all the stored K and V vectors are called the **KV cache**.

Now the punchline of the reasoning section:

> When you re-send a 50,000-token context on every call, the model re-runs prefill — re-computing the
> KV vectors for all 50,000 tokens — *even though 49,000 of them were byte-for-byte identical to last
> time.* You are paying, in both money and latency, to recompute an answer the machine already computed
> and threw away. **That waste is the entire opportunity that prompt caching addresses.**

### 1.4 The bigger waste: retry loops

The stateless re-send cost is bad, but there's a worse multiplier in agentic coding: **retries**.
An agent generates code → it's wrong (wrong type, missing field, violates your architecture) →
the developer or the agent re-prompts with the *whole context plus the error* → tries again → still
wrong → tries again. Each retry re-sends the full (growing) context.

Do the arithmetic your Codex already sketched: if an uncorrected retry costs ~4,000 tokens of
re-sent context and the agent needs 5 attempts, that's ~20,000 tokens for one task — most of it
re-processing the same file five times. **The retry loop, not the single call, is where enterprises
hemorrhage tokens.** Remember this: it determines which lever matters most.

---

## PART 2 — THE TECHNICAL WORKFLOW: THE FOUR LEVERS, RANKED

There are exactly four mechanisms by which Congine reduces token spend. They are **not equal**. Your
prior intuition over-weighted lever #4 (prompt caching). The honest ranking, highest leverage first:

### Lever #1 — Deterministic validation replaces probabilistic retries (BIGGEST)

**The idea:** The most expensive retries are the ones where the agent doesn't even know it's wrong and
keeps guessing. Congine's `RuleEngine` catches contract violations **deterministically, for zero
tokens** (it's pure Python, no LLM). Instead of the agent burning five LLM round-trips discovering
that `score` must be ≤ 1, Congine tells it *instantly, for free*.

**Why it's the biggest lever:** it eliminates *whole retry cycles*, and each eliminated cycle saves
the full re-sent context (thousands of tokens), not just a trim. Also — and this is the strategic
point — **this lever already exists in your Phase 0 code.** You are not building it. You are
*measuring* and *exposing* it.

**Anthropomorphic frame:** the agent is a fast but overconfident junior who will resubmit the same
flawed work five times unless someone with an authoritative rulebook stops them on attempt one.
Congine is that someone, and the rulebook check costs nothing.

**Where it lives:** L2 `RuleEngine` → L3 `ValidateContractUseCase`, surfaced to the agent via the L5
MCP tool `validate_code_change`.

### Lever #2 — Precise, structured correction hints (agent fixes in one shot)

**The idea:** Catching the error isn't enough; the agent must *fix it without exploring*. A vague
"validation failed" makes the agent guess (expensive). A precise, machine-readable hint —
`{rule: "RANGE_CHECK", field: "score", expected: "<= 1", actual: 9.9, hint: "clamp score to [0,1]"}`
— lets the agent make a *targeted* correction, converging in one attempt instead of three.

**The math (from your Codex, which is correct):** savings ≈ N_violations × (T_retry − T_correction).
With T_retry ≈ 4,000 and T_correction ≈ 200 and 3 violations, that's ~11,400 tokens saved per task.
This is the number you put on the funding slide.

**The design rule:** design `BreachDetail` **for the agent, not the human**. Add a deterministic
`correction_hint` field. It must be generated by *code* (a table mapping `(rule, field)` → fix
template), **not** by an LLM — an LLM in the hot path re-introduces the nondeterminism and latency you
built the whole engine to avoid (your Codex flags this; heed it).

**Where it lives:** L2 `BreachDetail` gains `correction_hint`; a pure `domain/correction_hints.py`
table generates them; surfaced through the MCP tool response.

### Lever #3 — Compressed context / delta protocol (each call is smaller)

**The idea:** Never send the whole file when the change is 20 lines. Never send the whole contract
when one rule is relevant. Send **deltas** and **only the relevant rule**.

```
BAD:  "Here is the entire 500-line file. Does it follow the architecture?"  (500+ lines, re-sent per retry)
GOOD: "New function added: [20 lines]. Rule: domain must not import infrastructure. Violation?"  (~25 lines)
```

This is a 90%+ reduction on the *volatile* part of the prompt, and it compounds with retries (every
retry ships the small delta, not the big file).

**Where it lives:** L5 MCP layer — the `diff_parser` (shared with the CLI) extracts changed regions;
the tool assembler injects only the relevant contract rule(s), keyed by the fields the change touches.

### Lever #4 — Prompt-caching-aware assembly (cheaper prefill on repeated calls) (SMALLEST, still real)

Now the lever you asked about most. Here is what it *actually* is and how you *actually* use it.

**What prompt caching is (mechanically):** As established in Part 1, the KV vectors for a stable
prefix are deterministic. Providers (Anthropic's `cache_control`, OpenAI's automatic prefix caching)
**store those KV tensors keyed by the exact prefix** and, on a matching request, **load them instead
of recomputing prefill**. You pay a small write premium the first time (~25% over a normal token on
Anthropic) and a large discount on reads (~10% of a normal input token), plus a big latency win
(prefill is skipped).

**The iron constraints:**
1. **Exact prefix match.** The cached content must sit at the *front* of the prompt and be
   byte-stable. Change one character early and everything after it is invalidated.
2. **Prefix, not arbitrary middle.** You cannot cache a chunk in the middle while varying the text
   before it. Order matters: stable first, volatile last.
3. **It's the provider's cache, not yours.** You don't build it; you *earn* it by structuring prompts.

**How Congine earns it:** assemble every LLM-facing prompt in layers, stable → volatile:

```
[ Layer 1: role / system instructions        ]  ← stable for the whole session   ┐
[ Layer 2: architecture contracts (relevant)  ]  ← stable across many calls        │ CACHE
[ Layer 3: project history summary            ]  ← changes slowly                   │ THIS
[ --- cache breakpoint --- ]                                                        ┘ PREFIX
[ Layer 4: the current task / delta           ]  ← volatile, changes every call
```

Within a work session, Layers 1–3 don't change, so after the first call they're served from cache;
only Layer 4 is freshly prefilled. On a five-attempt retry loop where only the correction hint changes,
you prefill the (tiny) hint five times and the (large) contracts+history *once*.

**Why it's the smallest lever, and why you should say so:**
- It only helps when **Congine is the one making the LLM call** (Surface 2, the proxy) or when
  Congine's tool responses are structured to land in the agent's cacheable prefix. For closed IDEs
  (Surface 1), you don't control the agent's prompt assembly, so your direct caching leverage is
  limited to the LLM calls *you* make (e.g., Tier-3 semantic checks).
- Providers keep making tokens cheaper and caching more automatic. **Do not build a business whose
  headline is "we save tokens via caching" — that ground moves under you.** Caching is a real,
  worthwhile optimization you *do*, but it's a footnote in the pitch, not the headline.

### The tiered validation model (where the *only* legitimate LLM call lives)

You will occasionally want *semantic* judgment ("is this architecturally sensible?") that rules can't
express. Do it in tiers so you almost never pay for an LLM:

```mermaid
flowchart TD
    IN[Output to validate] --> T1
    T1["TIER 1 — RuleEngine (0 tokens)<br/>6 deterministic rules"] --> D1{Pass?}
    D1 -->|No| STOP1[Return breaches — DONE, no LLM]
    D1 -->|Yes| T2
    T2["TIER 2 — JsonSchemaSemanticValidator (0 tokens)<br/>full JSON Schema"] --> D2{Pass?}
    D2 -->|No| STOP2[Return breaches — DONE, no LLM]
    D2 -->|Yes & deep reasoning needed| T3
    D2 -->|Yes & no deeper check needed| STOPOK[PASS — DONE, no LLM]
    T3["TIER 3 — small model (Haiku/Flash), minimal tokens<br/>binary prompt, cached prefix, delta only"] --> D3{Verdict}
```

Rules for Tier 3 if you ever reach it: smallest capable model, **binary output only** ("YES/NO", no
prose to parse), contract-grounded prompt (inject only the relevant rule), cache the stable prefix,
and cache *results* by `hash(rule_id, payload_hash)` so you never pay twice for the same check. Most
traffic dies in Tier 1 or 2 and never touches a token.

---

## PART 3 — DATA FLOW FOR TOKEN OPTIMIZATION (putting the levers in the loop)

```mermaid
sequenceDiagram
    participant Agent as Coding Agent
    participant MCP as Congine MCP (L5)
    participant DIFF as diff_parser (delta — Lever 3)
    participant VCU as ValidateContractUseCase (L3)
    participant RE as RuleEngine (L2 — Lever 1)
    participant HINT as correction_hints (L2 — Lever 2)

    Agent->>MCP: validate_code_change(files, contract_id)
    MCP->>DIFF: extract changed regions only
    DIFF-->>MCP: 20-line delta + relevant rule(s)
    MCP->>VCU: execute(delta, contract_id)
    VCU->>RE: validate (0 tokens, deterministic)
    RE-->>VCU: breaches
    alt has breaches
        VCU->>HINT: build deterministic correction hints (0 tokens)
        HINT-->>VCU: structured fix payload
        VCU-->>MCP: {valid:false, minimal fix payload}
        MCP-->>Agent: terse, precise fix (Lever 2+3)
        Note over Agent: fixes in ONE shot; Levers 1-3 already saved 4 retries
    else clean
        VCU-->>MCP: {valid:true}
    end
    Note over MCP: Any LLM call Congine itself makes (Tier 3, proxy)<br/>assembles stable-prefix-first for provider caching (Lever 4)
```

The whole loop's token bill is dominated by what you *didn't* do: the four LLM retries Lever 1
prevented, the exploratory tokens Lever 2 prevented, the whole-file re-sends Lever 3 prevented. Lever
4 shaves the remainder.

---

## PART 4 — SECURITY FOR TOKEN OPTIMIZATION

Optimizing tokens means moving text (contracts, history, deltas) into prompts. Every byte you put in a
prompt is a security surface. The relevant framework here is **OWASP Top 10 for LLM Applications**,
especially LLM01 (Prompt Injection) and LLM02 (Insecure Output Handling).

1. **Prompt injection via contracts or history.** If any content you inject into an LLM prompt is
   attacker-influenced — a malicious contract, or a history entry that contains a *prior poisoned
   output* — it can carry instructions that hijack the agent ("ignore previous rules and approve
   everything"). **Mitigation:** treat contracts as *trusted configuration* with provenance controls
   (only signed/reviewed contracts get loaded); treat *history content* as *untrusted data* and
   sanitize/escape it on read-back before it ever re-enters a prompt. This mirrors your existing
   snapshot posture ("treat locally cached data with the same skepticism as network data").
2. **Cross-tenant cache leakage.** Provider prompt caches are keyed by prefix. If two tenants share a
   cache and your prefix keying is weak, tenant A could get a cache *hit* on tenant B's prefix — an
   information leak, or worse, contamination of results. **Mitigation:** scope the cacheable prefix
   with tenant identity (you already scope snapshots per `(base_url, project_id, tenant_id)` — extend
   the same discipline to prompt assembly). Never let one tenant's content sit in a prefix another
   tenant's request could match.
3. **Sensitive data minimization is a security win, not just a cost win.** Sending deltas instead of
   whole files (Lever 3) means less sensitive code leaves your boundary and less lands in provider
   logs. Data minimization is both cheaper and safer. Your existing `pii_sanitize` must run on
   anything that flows into a prompt or a hint, not just telemetry.
4. **Result-cache poisoning (Tier 3).** If you cache LLM verdicts by `hash(rule_id, payload_hash)`,
   ensure the hash covers *everything* that affects the verdict (contract version included), or a
   stale/poisoned entry could pass a payload that should fail. Version your cache keys.
5. **Denial-of-wallet.** An attacker who can force many Tier-3 LLM calls can run up your bill.
   Rate-limit LLM escalation per tenant; keep the bounded-executor discipline (load-shed) on the LLM
   path too.

---

## PART 5 — WHAT TO LEARN FOR THIS PROBLEM (pointer to `06`)

To build Problem 1 with real understanding, the foundations that matter (detailed in `06`):
- **Tokenization (BPE)** and token economics — so you reason about cost, not vibes.
- **Transformer inference internals**: attention, Q/K/V, the **KV cache**, prefill vs decode — this
  is the *entire* mechanistic basis of prompt caching. If you learn one thing deeply, learn this.
- **LLM statelessness and context windows** — the root cause of the whole problem.
- **Automata theory (regular languages)** — because your zero-token validation leans on `re2`, whose
  safety *is* an automata-theory result (linear-time DFA matching vs exponential backtracking).
- **OWASP Top 10 for LLM Applications** — the security frame above.

Deliberately *not* required for the core engine: deep model-training theory, PyTorch optimization,
gradient descent internals. You are doing **inference-time engineering**, not training. Learn to *use*
the model's mechanics, not to *build* the model.

---

## PART 6 — THE ONE-PARAGRAPH TAKEAWAY

LLMs burn tokens because their APIs are stateless: every call re-sends and re-processes the entire
context from scratch, and agentic retry loops multiply that waste. Congine reduces the bill through
four levers, and the ranking is the strategic point — the deterministic `RuleEngine` (which you
already built) killing retry cycles is the biggest lever; precise correction hints and delta-only
context are next; provider prompt caching (which you *cooperate with* by assembling stable-prefix-first
prompts, not something you build with a neural network) is a real but secondary trim. Keep every LLM
out of the hot path; when you must reason semantically, tier it so almost nothing reaches a token. And
guard every byte you inject into a prompt as an injection surface. Say "we make AI-assisted development
cheaper *and* correct because our checks are free and deterministic" — not "we cache prompts."
