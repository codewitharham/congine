# CONGINE — CORE ENGINE REBUILD: START HERE

**Author's framing:** Written as a principal architect handing the core engine to a new
engineer taking ownership. Read this document *first and completely*. It reframes the vision
before you touch the deeper docs, and it corrects three misconceptions that will otherwise
waste months of your life. Estimated reading time: 20 minutes.

**Generated:** 2026-07-16
**Scope:** Core engine only. Control plane, blast radius, and go-to-market are deliberately out of scope, as you asked.

---

## 0. THE SITUATION, STATED PLAINLY

You lost the chat threads that held the *forward* product vision. You did **not** lose the
product. The product's Phase 0 core exists in code and is well-tested (the audit files prove
this). What you lost was the *narrative* connecting the code you have to the three big problems
you want to solve next. This document set rebuilds that narrative from the ground up.

There are eight documents. Read them in order:

| # | Document | What it gives you |
|---|----------|-------------------|
| 00 | **START_HERE** (this file) | Orientation + the 3 critical corrections + funding verdict at a glance |
| 01 | `01_CORE_ENGINE_ARCHITECTURE.md` | Task 1 — full architecture, all 3 problems mapped onto components, data-flow + workflow diagrams |
| 02 | `02_PROBLEM_TOKEN_OPTIMIZATION.md` | Problem 1 — why LLMs burn tokens, prompt caching internals, the *four* real levers |
| 03 | `03_PROBLEM_TRACKING_HISTORY.md` | Problem 2 — why memory is hard, the three stores, retrieval + injection |
| 04 | `04_PROBLEM_MULTI_AGENT_NORMALIZATION.md` | Problem 3 — "do we train the engine?" answered; adapters + capability profiles |
| 05 | `05_IMPLEMENTATION_ROADMAP.md` | Task 2 — strict build order (Phases A→F), per-phase steps, done-tests, security frameworks |
| 06 | `06_FOUNDATIONS_AND_LEARNING_PATH.md` | Task 3 — the math/CS/LLM/security foundations, each tied to *your own code*, mapped to phases |
| 07 | `07_TIMELINE_AND_FUNDING_VERDICT.md` | Task 4 — realistic timeline + candid answer on whether the core engine can raise |

---

## 1. WHAT CONGINE ACTUALLY IS (the anchor sentence)

Everything the Codex and the mental-model doc say collapses to this:

> **Congine is a deterministic firewall for the output of AI systems. It intercepts a value,
> checks it against a contract you wrote, and decides — in under 100ms, without crashing your
> app — whether to pass it, degrade it, or block it.**

Hold on to the word **deterministic**. It is not decoration. It is the entire commercial reason
the product can exist. A compliance lead cannot ship "our AI outputs are 95% likely to follow
our rules." They need "they follow the rules or they are blocked." Determinism is the moat.

Here is the trap you must not fall into: **the moment you make the *core engine* itself depend
on an LLM to make its decisions, you have thrown the moat in the river.** You will see, when we
get to token optimization, that people's instinct is "use an AI to check the AI." Resist it. The
core engine's verdicts come from code (the 6-rule `RuleEngine`, JSON Schema), which is why they
are fast, free, and repeatable. LLMs appear only at the *edges* of the system, never at its heart.

---

## 2. THE THREE CORRECTIONS (read these twice)

Your prompt contains three beliefs that are *directionally* right but *mechanically* off. If you
build on the beliefs as stated, you will build the wrong thing. Here they are, corrected.

### Correction 1 — "Our engine implements prompt caching to save tokens"

**What you believe:** Congine internally performs prompt caching, using something like a neural
network, to reduce token usage.

**The reality:** Prompt caching is not something *you* implement inside your engine with a neural
network. It is a feature offered by the **LLM provider** (Anthropic, OpenAI) at the inference
layer. It works by storing the transformer's internal computation (the *KV cache*) for a stable
*prefix* of the prompt, so that repeated calls with the same prefix skip re-computing it. Your
engine does not *build* the cache — it *earns* the cache by structuring its requests so the stable
parts (contracts, history summaries) sit at the front and never change, and the volatile part (the
current task) sits at the end.

**Why this matters:** If you think caching is your algorithm, you'll try to write it and fail. If
you understand it's the provider's mechanism that you *cooperate with*, you'll design your prompt
assembly correctly. And — critically — you'll realize prompt caching is only **one of four** token
levers, and *not the biggest one*. The biggest lever is your *existing deterministic engine* killing
retry loops. Full explanation in `02`.

### Correction 2 — "The developer's prompt goes into our engine, and our engine drives the coding agent"

**What you believe (the proxy model):** Developer → Congine → coding agent (Claude Code, Cursor)
→ back to Congine → developer. Congine sits *in front of* the agent, holding the primary prompt,
re-looping the agent until the job is done.

**The reality:** You cannot sit in front of a closed agentic IDE like Cursor or Claude Code. They
are not libraries that call your function — they are applications that *write files directly*. You
have no wire to intercept. This is the single most important structural fact about your integration,
and your own Codex already names it: *"they bypass your guard decorator entirely because they don't
call your Python functions. They write Python files."*

**The correct model (the tool/sidecar model, via MCP):** You do not wrap the agent. You give the
agent a **tool it can call** during its own reasoning loop. The agent stays in charge; Congine
becomes a service the agent consults — *"before you write this code, ask Congine if it's allowed."*
Control inverts. The agent calls `validate_code_change`, Congine returns a verdict + a precise
correction, and the agent decides what to do with it.

There is a narrow case where the proxy model *does* work: when the developer is calling a **raw LLM
API** (not a closed IDE), Congine can genuinely sit in the middle. That's the LangChain-handler
pattern you already have. So the honest answer to your "where does the primary prompt go?" question
is: **it depends on the integration surface**, and there are exactly two, explained fully in `01`.

The short version: **for coding agents, Congine is a tool the agent calls, not a proxy the prompt
flows through.** Design for that and everything downstream gets simpler.

### Correction 3 — "To normalize different coding agents, we train our engine on each agent's patterns"

**What you believe:** To bring Claude, GPT/Codex, and open-source agents to the same performance
level, Congine must *learn* each agent's behavior over time — implying model training.

**The reality:** No. Not in the machine-learning-training sense, and definitely not first.
Normalization comes from three *deterministic* mechanisms, in this order:

1. **The contract is the great equalizer.** Every agent's output is judged against the *same*
   contract. You don't need to understand the agent; you need to hold every agent to one standard.
   This already exists in Phase 0.
2. **A thin per-agent adapter** (a translation layer — the same Ports & Adapters pattern your whole
   codebase already lives by). It speaks each agent's dialect on the way in and normalizes output on
   the way out. Zero training. Just translation.
3. **Empirical capability profiles** built from your *own telemetry* (the history system from
   Problem 2). Over time you learn, statistically, "GPT fails contract-type X 40% of the time,
   Claude 8%" — and route accordingly. This is *statistics over your event log*, not deep learning.

So the connective tissue of your whole product is: **History (Problem 2) feeds the profiles that
power Normalization (Problem 3), and Normalization ensures the token savings (Problem 1) hold no
matter which agent is used.** Training a model is a Phase-3-or-never concern. Full explanation in `04`.

---

## 3. HOW THE THREE PROBLEMS ACTUALLY RELATE

You listed three problems as if they were parallel. They are not parallel — they are *layered*,
and the order is forced by dependency:

```
                 ┌─────────────────────────────────────────────┐
                 │   PROBLEM 1: TOKEN OPTIMIZATION              │
                 │   (deterministic validation kills retries;  │
                 │    caching + compression trim the rest)     │
                 └───────────────▲─────────────────────────────┘
                                 │ needs the MCP surface to
                                 │ reach the agent in-loop
                 ┌───────────────┴─────────────────────────────┐
                 │   THE MCP SURFACE (enabling substrate)      │
                 │   the engine's mouth: how it talks to agents│
                 └───────────────▲─────────────────────────────┘
                                 │
        ┌────────────────────────┴───────────────────────────────┐
        │                                                          │
┌───────┴──────────────────┐            ┌──────────────────────────┴───────┐
│ PROBLEM 2: HISTORY        │  feeds →   │ PROBLEM 3: NORMALIZATION         │
│ (persistent memory: the   │  telemetry │ (contracts + adapters + profiles │
│  event log + arch graph)  │            │  built FROM the event log)       │
└───────────────────────────┘            └──────────────────────────────────┘
                    ▲
                    │ all three stand on
        ┌───────────┴───────────────────┐
        │ PHASE 0 CORE (already built):  │
        │ RuleEngine, guard, executor,   │
        │ cache, breaker, snapshots      │
        └────────────────────────────────┘
```

Read that top to bottom: token optimization *needs* a way to reach the agent (the MCP surface);
the MCP surface and both other problems *need* the Phase 0 core; and Problem 3 *cannot be smart*
until Problem 2 has been collecting telemetry for a while. This is why the roadmap in `05` builds
the MCP surface and the history store *before* it builds anything clever.

---

## 4. FUNDING VERDICT AT A GLANCE (full version in `07`)

You asked whether the core engine alone is enough to raise. My candid, one-paragraph answer, with
the full argument and caveats in `07`:

**The core engine alone is necessary but not sufficient — a validation library is not yet a
company, and "output validation" already has competitors (Guardrails AI, NeMo Guardrails).** What
*is* fundable is the *combination* you're actually building: deterministic **architectural-contract
enforcement wired into the coding-agent loop via MCP**, with the beginnings of project memory. The
demo that raises money is one specific, showable moment: *connect Congine's MCP server to Claude
Code, watch the agent try to violate your architecture contract, watch Congine block it in-loop and
hand back a precise fix, watch the agent correct in one shot — and put the token-savings number on
screen.* That moment requires Phases A + B and ideally C + partial D from the roadmap. Lead with the
category ("enforcement/governance for AI-assisted development"), not the feature ("token
optimization") — providers keep making tokens cheaper, so token savings is a *benefit you cite*, not
a *moat you defend*. This is an engineering assessment, not financial or legal advice.

---

## 5. THE ONE HABIT THAT WILL SAVE YOU

Your Codex nailed this and I'm repeating it because it's the thing that actually keeps founders
un-stuck. Before every work session, answer three questions in writing:

1. **What is the ONE thing I am building right now?** (A named component, not "improve the system.")
2. **What is the exact test that proves it's done?** (A specific assertion, not "it works.")
3. **What am I explicitly NOT touching this session?** (Name it, to kill scope creep.)

If you can't answer all three, you're not ready to code — you're ready to *think*. That's fine.
Thinking is the job too. Now go read `01`.
