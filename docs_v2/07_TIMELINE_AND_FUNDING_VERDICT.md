# 07 — TIMELINE AND FUNDING VERDICT (Task 4)

**Purpose:** A realistic timeline for building the core engine (per phase and per problem), and my
candid, architect-to-founder assessment of whether the core engine alone can raise funding — with the
specific demo that would.

**Important framing.** I'm giving you an engineering and product-strategy view, the kind a senior
technical co-founder would give across the table. **This is not financial or legal advice, and it is not
a valuation.** Fundraising outcomes depend on your team, your traction, market timing, and your investor
network — things a document can't see. Take the timeline as planning scaffolding to adjust against your
real velocity, not a promise.

---

## PART 1 — TIMELINE

### 1.1 Assumptions (state these to yourself honestly, and adjust)

I'm estimating against a specific scenario. Where your reality differs, scale accordingly.

- **Team:** 1–2 engineers. The Builder's Codex reads as largely one founder-engineer with strong
  fundamentals.
- **Availability:** *part-time / not-full-time.* You said you have "other daily essentials" — I'm taking
  that at face value. Part-time roughly halves throughput versus full-time and, more importantly, adds
  *context-switching cost* (re-loading the problem each session), which is why the memory/history habit
  matters even for *you*.
- **Skill:** competent with the architecture (the Phase 0 code proves this) but *learning* the new
  domains (MCP, LLM-inference internals, the security frameworks) alongside building — so some weeks
  include study, not just code.
- **Definition of a "week":** a calendar week of part-time work, not a 40-hour sprint. Ranges are wide on
  purpose; treat the low end as "if it goes smoothly and you already know the foundation," the high end as
  "if you're learning the foundation as you build" (which, per `06`, you partly are).

### 1.2 Per-phase estimates (calendar, part-time)

| Phase | Scope | Part-time estimate | What drives the range |
|---|---|---|---|
| **A** | Harden Phase 0 debts + CLI + `diff_parser` | **2–4 weeks** | Debt fixes are small & known; CLI is straightforward; low end if you don't refactor beyond the bugs |
| **B** | MCP server + tools + prompt template + integration test | **3–5 weeks** | Learning MCP SDK + protocol; the prompt-template design (making the agent *call* the tool) is subtle and worth iterating |
| **C** | SQLite WAL event store + extended event + history queries | **3–5 weeks** | DB/WAL mechanics + tamper-evidence + erasure design; low end if you keep Phase-1 queries simple (no vector search) |
| **D** | Correction hints + delta protocol + cached assembly + tiers + instrumentation | **4–6 weeks** | The hint *table* and delta protocol are real work; cached-prefix assembly needs the KV-cache understanding from `06` |
| **E** | Arch graph + arch-validate + pattern detection + agent adapters + profiles | **6–10 weeks** | The biggest phase: two tracks, graph algorithms, one adapter per agent, and it needs *accumulated* data to be meaningful |
| **F** | Adaptive routing + contextual bandit + drift re-profiling | **4–6 weeks** | Optional pre-funding; only meaningful once profiles are populated |

### 1.3 Per-problem view (how your three problems map onto the calendar)

- **Problem 1 (Token Optimization):** genuinely *usable* the moment Phase B ships (deterministic in-loop
  validation already cuts retries), *fully realized* at the end of Phase D. So: **partial value ~end of B
  (weeks ~5–9 cumulative), full value ~end of D (weeks ~12–20 cumulative).**
- **Problem 2 (Tracking History):** foundation at end of Phase C (**~weeks 8–14 cumulative**), intelligence
  (graph + patterns) folded into Phase E.
- **Problem 3 (Normalization):** first form (contract = one standard) exists *today*; real form (adapters +
  profiles) at end of Phase E (**~weeks 14–24 cumulative**); routing in optional Phase F.

### 1.4 The number that matters: time to a fundable demo

The demo that raises money (Part 2) needs **A + B + C + partial D**. Adding those:

- **Part-time:** roughly **3–4 focused months** (≈ 12–18 calendar weeks), assuming you don't stall on the
  learning curve.
- **Full-time (if you could go heads-down):** roughly **8–10 weeks**.

Everything after that (rest of D, E, F) *strengthens* the raise but isn't required to start conversations.
**Do not build F before you've raised.** It's the most exciting part and the least necessary — building it
first is a classic way to burn your runway polishing a feature investors didn't need to see.

### 1.5 A scheduling warning specific to your situation

Part-time + solo + learning-as-you-go has one failure mode above all others: **losing the thread between
sessions** (which is, ironically, the exact human-memory problem your Problem 2 solves). Mitigations,
cheap and high-return: keep a running build log (your own event log); end every session by writing the
*next* concrete step; and use the three-question habit from `00` §5 to start each session with a decision,
not a fog. This is worth more to your timeline than any tooling.

---

## PART 2 — THE FUNDING VERDICT

### 2.1 First, the honest praise (so you trust the criticism)

I want to be straight about what's genuinely good, because it's real and it matters. Your Phase 0
engineering is **not** a toy. The audit files show a bounded-latency executor with load-shedding, `re2`
for linear-time regex (ReDoS-immune), a circuit breaker, an integrity-checked snapshot loader that
defends symlink/TOCTOU attacks, PII-safe telemetry, and a clean hexagonal architecture where features
attach at the edges without touching the core. That is *disciplined systems work*, and it's rarer than it
should be. The Builder's Codex is honest and well-reasoned. **You can build.** Investors who look closely
will see that, and it de-risks the "can this team execute" question, which is half of an early raise.

### 2.2 The hard part: a validation library is not yet a company

Now the candid part. **The core engine, described as "an output-validation SDK," is necessary but not
sufficient to raise on its own.** Two reasons:

1. **The category "validate/guard AI outputs" is contested.** Guardrails AI, NeMo Guardrails, and others
   already occupy "put rules around LLM outputs." A reviewer's reflex will be "how is this different from
   Guardrails?" If your answer is "it's faster and deterministic," that's a *feature* argument, and feature
   arguments are weak fundraising positions — they invite "so they'll add that."
2. **A library is a tool, not a business.** Tools become businesses when they own a *workflow* and a
   *category*, not when they win a benchmark.

So if you pitch "deterministic output validation," you're pitching into a crowded lane with a feature
differentiator. That's the version that struggles.

### 2.3 What IS fundable: the combination you're actually building

Here's the reframe, and it's not spin — it's what your own architecture already points at. The fundable
thing is the *combination*:

> **Deterministic enforcement of architectural contracts, wired directly into the coding-agent loop via
> MCP, with the beginnings of persistent project memory.**

That is a *different, less-crowded category*: **governance / enforcement for AI-assisted software
development.** As teams hand more code to Claude Code, Cursor, and Copilot, the unsolved problem isn't
"generate code" (the agents do that) — it's "make sure the generated code obeys *our* architecture, *our*
rules, *our* standards, deterministically, and remember what we decided." Almost nobody validates an
agent's change *against the current architecture* in-loop. Your arch-graph capability (Problem 2, Store 2 →
Phase E) is the piece no generic guardrail has. **That's the wedge.**

And critically: the enforcement is *deterministic*, which is exactly what a compliance/security buyer needs
and exactly what a probabilistic "AI reviews AI" competitor can't promise. Your moat and the category's
requirement are the same property.

### 2.4 The demo that raises the money (be specific)

Investors fund a *moment of "oh, I'd use this,"* not a feature list. Build toward this one scene:

1. Connect the Congine MCP server to Claude Code (or Cursor) on a real repo with an architecture contract
   (e.g., "domain must not import infrastructure," "all API responses match schema X").
2. Ask the agent to make a change that *would* violate the architecture.
3. Watch Congine **block it in-loop** and hand back a **precise, deterministic correction hint**.
4. Watch the agent **fix it in one shot**.
5. Put the **token-savings number** on screen (`savings ≈ N_violations × (T_retry − T_correction)` from
   `02`/`05`) — "this task would have taken the agent 5 tries and N tokens; with Congine it took 1 try and
   M tokens, *and* the result provably follows your architecture."

That scene shows enforcement (the category), determinism (the moat), and token savings (the benefit) in
fifteen seconds. It requires **A + B** and is much stronger with **C + partial D** (so you can show memory
and real savings). It does **not** require E or F.

### 2.5 Two strategic corrections to your pitch instinct

1. **Lead with the category, not the token feature.** You've been framing token optimization as the
   headline. It's a *fantastic supporting metric* (the cost math is visceral and CFO-friendly), but it is
   **not a defensible headline**, because providers keep cutting token prices and adding caching
   themselves — the ground moves under a "we save tokens" pitch. Headline: *"deterministic enforcement +
   memory for AI-assisted development."* Token savings is the proof point you cite, not the moat you
   defend.
2. **The multi-agent "management system" is a vision slide, not a critical-path deliverable.** It's your
   most ambitious idea and it's genuinely compelling *as a story* ("we normalize any agent to your
   standard"). But it's the least defined and the furthest out (Phase E/F). Put it on the roadmap slide as
   "where this goes," and be honest it's ahead. **Do not build the routing/bandit layer (F) before you
   raise** — it's runway spent on a slide you can *tell* instead of *build*.

### 2.6 Caveats I can't see past

- **Stage matters.** "Fundable" here means it can support real pre-seed / seed conversations with a crisp
  demo and (ideally) a design partner or two. It does not mean the core engine alone commands a large
  round without traction.
- **Design partners beat features.** One or two teams saying "we use this on our repo and it caught real
  violations" is worth more than another feature. Prioritize getting the MCP tool into *someone's* real
  workflow (Phase B) over building E/F.
- **Geography and network.** Access to investors varies by where you are and who you know; a sharp demo and
  a real design partner travel across geographies better than anything else, which is another reason to
  optimize for the demo + a partner, not for feature count.
- **You still owe the non-engine story eventually.** Control plane, stability, packaging, pricing — out of
  scope here, but investors will ask "what's the company around the engine?" Have a one-slide answer even
  though you're not building it yet.

### 2.7 The verdict in one paragraph

The core engine *as a validation library* is necessary but not sufficient to raise — that lane is crowded
and a library isn't a company. But the core engine *as you're actually building it* — deterministic
enforcement of architectural contracts wired into the coding-agent loop via MCP, plus the start of persistent
memory — is a genuine, less-contested wedge in a real emerging category (governance for AI-assisted
development), and your determinism is simultaneously your moat and exactly what the buyer needs. It becomes
fundable at the moment you can show one specific scene: an agent blocked in-loop from violating your
architecture, corrected in one shot, with the token-savings number on screen. That scene needs Phases A + B
and is much stronger with C + partial D — realistically **3–4 focused months part-time, or ~8–10 weeks
full-time.** Lead with the category, cite token savings as the proof point, keep multi-agent normalization
as a vision slide, and don't spend runway on the routing layer before you raise. Your engineering is real
enough that the "can they build it" question is already half-answered — now make the "would anyone use it"
question answer itself with that demo. *(Engineering/strategy assessment, not financial or legal advice.)*
