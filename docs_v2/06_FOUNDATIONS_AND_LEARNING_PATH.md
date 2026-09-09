# 06 — FOUNDATIONS AND LEARNING PATH (Task 3)

**Purpose:** The core concepts you must actually understand to build this engine without getting stuck —
and, crucially, *why each one matters*, tied to your own codebase and mapped to the build phases from
`05`. This is the antidote to the "just learn LangChain, LangGraph, scikit-learn, PyTorch" advice you
correctly distrust. Those are tools; this is the foundation that lets you *use* tools without being
confused by them.

**The governing principle:** You are building an **inference-time, deterministic systems product**, not
training models. So your foundation is weighted toward **discrete math, theory of computation, systems,
and security**, with just enough **LLM-inference literacy** to reason about tokens and context — and
almost *no* deep model-training theory. The single most motivating fact in this whole document: **your
product's flagship safety guarantee (no ReDoS, via `re2`) is a theorem from automata theory.** The math
isn't academic decoration — it's already load-bearing in your code. Let's make every concept that concrete.

---

## HOW TO READ THIS

Five tiers, roughly in dependency order. Each concept has: **what it is (briefly)**, **why it matters
here (tied to your code)**, and **which phase needs it**. Learn a tier to *working familiarity*, not
mastery, then move on — you'll deepen by building. Don't try to learn everything before Phase A; learn
Tier 0 + the Phase-A slice, build, and pull the next slice as you go.

Security (Tier 4) is **threaded through every phase**, not saved for the end — you asked for this
explicitly, and it's correct: security bolted on afterward is the "vibe-coded app with vulnerabilities"
failure mode.

---

## TIER 0 — MATHEMATICAL & CS BEDROCK (underlies everything; start here)

### 0.1 Discrete mathematics: sets, relations, functions, logic, proof
**What:** The grammar of precise thinking — sets and membership, relations and functions, propositional
and predicate logic, basic proof technique.
**Why it matters here:** **A contract is a set of logical predicates over data, and validation is
predicate evaluation.** "`score` must be a number in [0,1]" is a predicate; the `RuleEngine` is a
predicate evaluator; a `BreachDetail` is a witness that a predicate was false. When you extend contracts
or reason about what they can express, you're doing predicate logic whether you name it or not. Sets also
underlie the enum rule (membership test) and the whole idea of "the set of valid outputs."
**Phase:** A (contracts, rule engine), throughout.

### 0.2 Theory of computation / automata: regular languages, DFA/NFA, the Chomsky hierarchy
**What:** Finite automata (DFA/NFA), regular languages, and the hierarchy of formal languages
(regular ⊂ context-free ⊂ context-sensitive ⊂ recursively-enumerable).
**Why it matters here — this is the one to internalize deeply:**
- **Your #1 safety guarantee IS an automata result.** `re2` guarantees *linear-time* matching because it
  compiles a regex to a finite automaton and runs it without backtracking. Classic backtracking engines
  simulate an NFA in a way that can blow up *exponentially* on crafted input — that's ReDoS, and it's the
  denial-of-service you already defend against by choosing `re2`. When someone asks "why can't a malicious
  contract hang your validator?", the answer is a theorem: regular-language recognition is O(n) on a DFA.
- **The Chomsky hierarchy tells you what contracts can and cannot express.** Regular languages (what
  regex/pattern rules capture) can't count arbitrarily nested structure; JSON Schema's structural checks
  go a bit further; some "architectural" constraints (balanced/nested dependency rules) are *beyond*
  regular and belong in the graph layer, not the regex layer. Knowing the hierarchy stops you from trying
  to express a context-free constraint with a regular tool and wondering why it won't work.
**Phase:** A (re2, pattern rules), E (what belongs in the graph vs the rule engine). *This is the single
best-motivated topic in your whole curriculum — study it against `pii_sanitize.py` and the pattern rule.*

### 0.3 Graph theory: DAGs, topological order, reachability, cycles
**What:** Directed graphs, directed *acyclic* graphs (DAGs), topological sorting, reachability,
cycle detection.
**Why it matters here:** **Your architecture's core rule — "dependencies point inward only" — is a DAG
constraint**, and the architectural graph (Problem 2, Store 2) is a literal directed graph. "domain must
not import infrastructure" = "no edge from a domain node to an infrastructure node"; "no circular
dependencies" = "the import graph must be acyclic." `validate_arch_usecase.py` (Phase E) is graph
algorithms: forbidden-edge checks, cycle detection, reachability. This is the theory behind your most
differentiating feature.
**Phase:** E (arch graph), and conceptually A (understanding the layer rule).

### 0.4 Probability & statistics: distributions, hypothesis testing, confidence intervals, Bayesian updating
**What:** Random variables and distributions, hypothesis testing (including the **Kolmogorov–Smirnov
test**), confidence intervals, and the Bayesian idea of updating a belief with evidence.
**Why it matters here:** **You already ship a KS test** — `KSDriftEngine` uses it to detect when a
distribution of outputs/violations has *drifted*. To use it well (and point it at agent performance in
Problem 3) you need to understand what "two samples come from the same distribution" means and when the
test is/ isn't meaningful (sample size!). Capability profiles (Problem 3) are statistical estimates —
success rates with uncertainty; small-sample profiles are noise, and you need enough stats to know it.
The optional contextual bandit (Phase F) is Bayesian-flavored (Thompson sampling literally samples from a
posterior).
**Phase:** E/F (profiles, drift, bandit); conceptually wherever `KSDriftEngine` appears.

### 0.5 Complexity & algorithms: big-O, amortized analysis, hashing, LRU/LFU
**What:** Asymptotic complexity, *amortized* analysis, hash tables, cache-eviction policies (LRU/LFU).
**Why it matters here:** Your **`LFUCache` gives O(1) get/put** — that's an amortized-analysis and
data-structure result, and it's *why* schema lookups don't slow the hot path. The **bounded executor**
enforces a latency budget — a complexity/systems guarantee. The **`payload_hash`** in the event log is
hashing for dedup and content-addressing. When you reason about "will this scale / stay under 100ms",
you're doing complexity analysis. Understanding amortized O(1) is what lets you defend "cached schema
lookup is free" honestly.
**Phase:** A/C/D (cache, executor, hashing), throughout.

---

## TIER 1 — LLM & INFERENCE INTERNALS (for Problems 1 & 3; inference literacy, NOT training)

### 1.1 Tokenization (BPE) and token economics
**What:** How text becomes tokens via byte-pair encoding; why a token ≠ a word; how you're billed.
**Why it matters here:** Token cost is your Problem-1 unit of account. You can't reason about savings if
you think in words. (See `02` Part 1.)
**Phase:** B/D (token optimization).

### 1.2 Transformer inference: attention, Q/K/V, the KV cache, prefill vs decode — **learn this deeply**
**What:** At inference, a transformer computes Query/Key/Value vectors per token per layer; attention lets
each token attend over prior tokens; the stored K/V vectors form the **KV cache**; **prefill** processes
the input prompt (compute-heavy), **decode** generates output token-by-token.
**Why it matters here:** **This is the entire mechanistic basis of prompt caching.** K/V for a stable
prefix are deterministic and reusable; providers cache them; you *earn* the cache by putting stable
content (contracts, history summary) first. If you learn one LLM-internals topic, learn this — it's the
difference between "prompt caching is magic we implement" (wrong, Correction 1) and "prompt caching is
provider-side KV reuse we cooperate with by structuring prompts" (right). Study it against `02` Levers.
**Phase:** D (caching, tiered validation), and conceptually B.

### 1.3 LLM statelessness, context windows, sampling determinism
**What:** API calls are stateless (no memory between calls); context windows are finite; sampling params
(temperature, top-p) control randomness.
**Why it matters here:** Statelessness is the *root cause* of both the token problem (Problem 1) and the
machine-memory problem (Problem 2) — the same fact drives two of your three features. Finite context is
*why* you must compact history (`03`) rather than dump it. And the fact that LLM output is *sampled*
(nondeterministic) is precisely why your deterministic core can't be an LLM — determinism is your moat.
**Phase:** B/C/D (tokens + history).

### 1.4 Just-enough training concepts (pretraining, fine-tuning, RLHF) — awareness only
**What:** A conceptual grasp of how models are pretrained, fine-tuned, and aligned (RLHF) — *why* they
behave as they do.
**Why it matters here (and the boundary):** You need enough to reason about *why* different agents differ
(Problem 3) and to explain to an investor why you don't train. You do **not** need optimization theory,
backprop internals, or PyTorch training loops for the core engine. **Explicitly resist the "learn PyTorch
to train a model" instinct** — building a learned component into the core would trade your determinism
moat for a research project you don't need (see `04` Part 1). Awareness, not expertise.
**Phase:** conceptual background for `04`; not on the build critical path.

---

## TIER 2 — SYSTEMS & DISTRIBUTED (for persistence, concurrency, scale)

### 2.1 Concurrency: threads, locks, the GIL, thread pools, races, deadlock
**What:** Threads and synchronization primitives (locks, **re-entrant locks/RLock**, semaphores), Python's
GIL, thread pools, race conditions, and deadlock.
**Why it matters here:** **Your `BoundedValidationExecutor` uses a thread pool with a re-entrancy guard**
— and the audit specifically calls out that a *non*-re-entrant lock there would deadlock on nested
validation (execution trace 3 / the RLock discussion). The cache priming lesson (never clear-then-refill)
is a race-condition lesson. When you add the SQLite store (Phase C), WAL exists precisely to let a writer
and readers proceed *concurrently* without blocking — a concurrency concept. Get comfortable with "what
happens if two threads hit this at once."
**Phase:** A (executor), C (WAL concurrency).

### 2.2 Databases: ACID, WAL, indexing, append-only / event sourcing, content-addressing
**What:** Transaction guarantees (ACID), write-ahead logging (WAL), indexing, the append-only/event-sourced
model (the log is the source of truth; state is derived), content-addressed storage (key by hash).
**Why it matters here:** This is the theoretical backbone of Problem 2. WAL is your Phase-C concurrency
answer; append-only + hashing is your tamper-evident, privacy-preserving event log; "state derived from
the log" is the event-sourcing mindset that makes the arch graph a *derived* (rebuildable) structure.
(See `03` Part 2.)
**Phase:** C (persistence), E (derived graph).

### 2.3 Distributed-systems basics (forward-looking): idempotency, delivery semantics, circuit breakers, backpressure, CAP
**What:** Idempotency, at-least-once vs exactly-once delivery, the **circuit breaker** pattern,
backpressure/load-shedding, and (when you go multi-node) the CAP theorem.
**Why it matters here:** **You already ship two of these** — `CircuitBreaker` (stops hammering a failing
dependency) and the bounded executor's **load-shedding** (backpressure). Understanding them lets you
extend them safely and explain your resilience story. CAP matters later, when the single-node SQLite store
becomes a distributed store (Phase 2/3 of history).
**Phase:** A (breaker, load-shed already present), later for multi-node.

### 2.4 Protocol design: JSON-RPC, stdio/SSE transports
**What:** Request/response protocol design; **MCP is built on JSON-RPC**; stdio vs HTTP/SSE transports.
**Why it matters here:** Phase B *is* protocol work — the MCP server speaks JSON-RPC over stdio/SSE, and
your `IMCPTransport` port abstracts the transport. Adapters (Problem 3) translate between MCP dialects.
Understanding the protocol layer keeps the MCP work from feeling like black magic.
**Phase:** B (MCP), E (adapters).

---

## TIER 3 — APPLIED AI ORCHESTRATION (the "frameworks" — LAST, and lightly)

These are the things social-media roadmaps put *first*. Put them **last**, and learn only what you'll use.
Learn them *after* Tiers 0–2 so you understand what they're doing under the hood instead of cargo-culting.

### 3.1 The MCP protocol + Anthropic MCP SDK — **the one framework you must actually learn**
**Why/Phase:** Phase B. This is your integration substrate. Learn it properly (it's small).

### 3.2 Retrieval & summarization patterns; embeddings + ANN (**Phase 3 of history only**)
**What:** Retrieval-augmented patterns, context summarization/compaction, and — *deferred* — embeddings
with approximate-nearest-neighbor indexes (cosine similarity, HNSW).
**Why/Phase:** Summarization/compaction is Phase C/E (compact history into a cheap prefix). Embeddings +
vector search are **explicitly deferred to Phase 3** — structured SQL queries answer your real questions
first (`03` Part 3, Rule 1). Do not reach for a vector DB early; it's the classic over-engineering trap.

### 3.3 LangChain / LangGraph — **optional; know the callback pattern, don't over-invest**
**Why/Phase:** You already integrate a LangChain callback handler (Surface 2). Understand the callback
lifecycle enough to maintain that integration. Beyond that, LangChain is optional — it's a convenience
layer, not a foundation, and your value is *below* it.

### 3.4 Contextual bandits / lightweight online decisioning (**Phase F only, optional**)
**What:** Multi-armed and *contextual* bandits; Thompson sampling / UCB; the explore/exploit tradeoff.
**Why/Phase:** The *correct*, lightweight tool for adaptive agent routing (Phase F) — a few dozen lines of
well-understood math, **not** deep RL or model training (`04` Mechanism 3). Learn only if/when you build F.

---

## TIER 4 — SECURITY (threaded through EVERY phase — not optional, not last)

You asked for security frameworks per phase; here are the disciplines, each mapped to where it bites.
Treat this tier as a *parallel track* you touch in every phase, per the security sections in `05`.

### 4.1 Threat modeling: STRIDE + attack trees
**What:** STRIDE (Spoofing, Tampering, Repudiation, Information disclosure, DoS, Elevation of privilege)
per component; attack trees to enumerate paths.
**Why/Phase:** Phase A baseline (model the existing surface), re-run at each new surface (B: MCP; C: the
store). This is *how you find* the threats the other disciplines defend.

### 4.2 OWASP Top 10 (web/API) + **OWASP Top 10 for LLM Applications** (the key one)
**What:** The web/API Top 10, and — most relevant to you — the LLM Top 10, especially **LLM01 Prompt
Injection** and **LLM02 Insecure Output Handling**.
**Why/Phase:** API Top 10 → Phase B (MCP HTTP/SSE endpoints). LLM Top 10 → Phases B/D/E (every prompt you
assemble is an injection surface; every agent output is untrusted). This is the security literacy most
specific to an AI product; read the LLM Top 10 in full.

### 4.3 Application security: input validation, output encoding, injection classes, authn/authz, secrets
**What:** Validate all external input (you have an engine — use it on your own MCP inputs), encode/escape
output, understand injection broadly, authenticate and authorize, and manage secrets (never in code/logs;
use a vault).
**Why/Phase:** B (validate tool inputs, authz at the boundary), C (least-privilege DB, tenant scoping),
E (per-agent credential isolation — extend the `StructuredLogger` secret blocklist to every new field).

### 4.4 Cryptography basics: hashing (SHA-256), HMAC, Merkle/hash chains, encryption at rest, TOCTOU/symlink attacks
**What:** Cryptographic hashing, message authentication (HMAC), tamper-evident structures (Merkle
trees / hash chains), encryption at rest, and time-of-check/time-of-use + symlink attacks.
**Why/Phase — with a great existing hook:** **Your snapshot loader already defends symlink and TOCTOU
attacks** (owner checks, symlink checks, envelope validation on locally cached data — execution
trace/threat notes). SHA-256 is your `payload_hash` (C); hash-chaining is your tamper-evident event log
(C, `03` §5.2); encryption at rest protects the store (C). Study TOCTOU against the snapshot loader — it's
a live example of this exact attack class in your own code.
**Phase:** C primarily; A for the existing snapshot defenses.

### 4.5 Supply-chain security: SBOM, dependency pinning, scanning
**What:** Software Bill of Materials, pinned dependencies, vulnerability scanning (`pip-audit`).
**Why/Phase:** Your dependency-light discipline is already a supply-chain posture. It bites hardest in
Phase E (open-source agent adapters pull larger surfaces) and whenever you add an optional extra.

### 4.6 Privacy engineering: PII handling, data minimization, GDPR erasure, tamper-evident audit
**What:** PII detection/redaction, data minimization, the "right to erasure," and audit-log integrity.
**Why/Phase:** **Your `pii_sanitize` is already privacy engineering.** It scales into a first-class concern
in Phase C (store hashes not payloads; the erasure-vs-immutability design in `03` §5.5). Enterprise buyers
will ask about all of this — designing it in early is a *sales* advantage, not just a compliance chore.

---

## THE PHASE → FOUNDATION MAP (what to learn *before* each build phase)

| Build phase | Learn first (minimum viable foundation) |
|---|---|
| **A** (harden + CLI) | 0.1 logic/sets, 0.2 automata (re2/ReDoS), 0.5 complexity (cache/executor), 2.1 concurrency (RLock), 4.1 STRIDE, 4.4 TOCTOU (snapshot) |
| **B** (MCP) | 1.1 tokens, 1.3 statelessness, 2.4 protocols/JSON-RPC, 3.1 MCP SDK, 4.2 OWASP API + LLM01, 4.3 authn/authz + input validation |
| **C** (history) | 2.2 DB/ACID/WAL/event-sourcing, 0.5 hashing/content-addressing, 4.4 SHA-256/Merkle/encryption, 4.6 minimization/GDPR |
| **D** (token depth) | 1.2 KV cache/prefill (deeply), 1.1 tokens, 3.2 summarization, 4.2 LLM01/LLM02, cache scoping |
| **E** (graph + adapters) | 0.3 graph theory (DAG/cycles/reachability), 0.4 statistics (profiles), Ports&Adapters/DDD, 4.2 zero-trust, 4.5 supply-chain |
| **F** (routing, optional) | 0.4 Bayesian, 3.4 contextual bandits, drift (KS) |

Learn Tier 0 broadly up front (it pays off everywhere), then pull each phase's row as you reach it. You do
**not** need to finish this curriculum before writing code — you need Tier 0 + the Phase-A row, then build,
then pull the next row. Depth comes from building against theory you half-know; that's normal and correct.

---

## THE TWO SENTENCES TO REMEMBER

**Your product is already standing on this math** — re2's safety is automata theory, the KS drift engine is
statistics, the O(1) cache is complexity analysis, the snapshot loader is TOCTOU-hardened cryptography-adjacent
systems work, and the layer rule is a graph constraint. So the foundations aren't a detour from building —
they're the names for what you've *already built*, which is exactly why learning them will make the rest of
the build stop feeling confusing. And weight your study toward **discrete math, computation theory, systems,
and security**, with just enough **inference-time LLM literacy** to reason about tokens and context — because
you are engineering a deterministic system that *uses* models, not training the models themselves.
