# PROMPT W1 — THE DOCUMENTATION SITE

## How to use

**Where:** Claude Code, at the monorepo root. Run §6 setup commands from
`WEB_ARCHITECTURE_AND_TOOLING.md` first.

**Attach:** `WEB_ARCHITECTURE_AND_TOOLING.md` (binding). Reads from repo:
`ARCHITECTURE_CURRENT.md`, `docs/_suite/gap/GAP3*` if it exists, the SDK source.

**Produces:** `apps/docs/` (Astro Starlight), `packages/design-tokens/`, `examples/`.

**Run one stage per session.** Six stages. Do not run them together.

---

```text
=== BEGIN PROMPT W1 ===
```

# ROLE

You are a staff engineer and technical writer building the **official documentation site for Congine** —
a deterministic output-governance SDK for Python. The site is the product's front door for every
developer who will ever evaluate or adopt it.

# TIME AND EFFORT

**TAKE AS MUCH TIME AND AS MANY SESSIONS AS YOU NEED. THIS IS EXPLICITLY AUTHORIZED AND EXPECTED. THERE
IS NO TIME PRESSURE.**

Run **one stage per session**. Complete it, verify it, report, stop. The previous attempt at this work
failed because six stages were collapsed into one generation; that failure mode is what the staging
prevents. If context runs low mid-stage, checkpoint to `apps/docs/PROGRESS.md` and report the resume
point. Never thin out a stage to finish it.

# THE ABSOLUTE RULE

**Document only what exists.** `ARCHITECTURE_CURRENT.md` §15 confirms these are NOT built: MCP server,
CLI, persistent event store, history queries, correction hints, architecture graph, agent adapters,
adaptive routing. §1: *"There is no server, no database, no CLI, no persistence."* Re-verified at
`6345a1e` — the absence list is unchanged.

Every page carries a status badge — `Available`, `Partial`, `Planned — Phase X`. Planned features live
in a **Roadmap** section and are written as *intent*, never as instructions. **Never write an install
guide, a code example, or an API reference for something that does not exist.** A developer who follows
instructions for a nonexistent feature does not come back.

# THE SECOND ABSOLUTE RULE — do not warn about a defect that is fixed

*Added 2026-08-17, against `6345a1e`.*

The engine has moved twice since this prompt was drafted: `49a2f93` closed all twelve
`ARCHITECTURE_CURRENT.md` §17 open questions, and `6345a1e` landed the eight-item P0 Trust-Critical
Hardening pass, and has since closed **P1 Structural Hardening** (`b482bc4`).
**`ARCHITECTURE_CURRENT.md`'s current-state header block and §16 reconciliation table are the
reconciliation record — read them before
Stage 1**, and check every warning you are about to write against it.

**The single biggest change to this prompt.** Stage 4 previously made the **union-type defect (D18)**
the centrepiece of the site's most important page: `{"type": ["string","null"]}` caused *silent
permanent degradation* of every validation against that contract. **It is fixed.** Unions are the
correct, enforced way to declare a nullable field. A docs site that still warns about it would be
telling developers to avoid the right answer.

What replaces it — and it is a better page, because it documents a working control rather than a trap:

| Retired | Current |
|---|---|
| "A union type silently degrades every validation forever" | Unions are **enforced**. A union containing an *unrecognised* member is refused at load |
| "Unenforced keywords are silently ignored" | They are still unenforced — but a contract using one is **refused at load** under default configuration, and **admitted** when an evaluator that enforces it is wired |
| "`region` is accepted but unread (D1)" | `region` is documented metadata; setting it **without** `CONGINE_BASE_URL` raises |
| — *(new)* | **Contract admission** (§13.8): seven refusal codes; a contract CONGINE cannot interpret never becomes active policy |
| — *(new)* | **Admission runs on the loader path only** (D17). A direct `schema_storage.put()` bypasses it. **This is the live warning that replaces D18** |
| — *(new)* | **`is_pass()` does not tell you whether the policy was evaluated.** Ask `is_enforced()` first (§11.2) |

Overstating a defect is the same failure as overstating a capability. Both are a surface that does
not match the system.

# VOICE

Technical and precise, warmed by metaphor **only where the metaphor explains a mechanism**. If you can
delete the metaphor without losing understanding, delete it. Second person, present tense, active voice.
Short sentences for instructions; longer ones for explanation. No marketing language anywhere in the
docs (the landing page is not in scope).

---

# STAGE 1 — SCAFFOLD AND DESIGN TOKENS

**Goal:** a running Starlight site with the Congine visual identity, and shared tokens the control
plane will inherit.

1. Scaffold Starlight into `apps/docs`, package name `@congine/docs`, **as an Nx project** in the
   existing npm + Nx workspace. Pin versions. **Do not introduce pnpm, do not create
   `pnpm-workspace.yaml`, and do not overwrite the root `package.json`** — see
   `WEB_ARCHITECTURE_AND_TOOLING.md` §1 and §6. Install with `npm ci`. Give the project a
   `project.json` declaring its targets, then confirm the dev and build targets work via
   `npm exec nx -- run docs:<target>` and record the exact target names you created. Never document
   a `pnpm dev:docs`-style script; no such script exists.
2. Create `packages/design-tokens` exporting both CSS custom properties and a TS object:
   - **Colour:** an ink/navy primary, one accent, a neutral ramp, plus **semantic** colours for
     `pass` / `breach` / `degraded` / `blocked` — these four recur across both sites and must be
     defined once here.
   - **Type:** IBM Plex Sans for UI/prose, IBM Plex Mono for code. (Matches existing Congine collateral.)
   - **Spacing, radii, elevation** on a consistent scale.
3. Wire the tokens into Starlight's theme. Light and dark, both deliberate.
4. Configure: site title, description, GitHub link, search, sidebar structure (Stage 2), code themes,
   copy buttons, and an `<Aside>`/badge convention for the four status labels.
5. Verify: build passes, both themes render, no console errors, Lighthouse ≥ 95 on the home page.

**Report:** the running command, the token names, and a screenshot description of the shell.

---

# STAGE 2 — INFORMATION ARCHITECTURE

**Goal:** the complete sidebar and every page stubbed, so the shape is reviewable before content exists.

Create every page as a stub with frontmatter, title, status badge and a one-line description.
**Nothing written yet.** The IA:

```
Start here
  What is Congine?              Available
  Why Congine?                  Available
  Installation                  Available
  Quickstart: first validation  Available
  Quickstart: first breach      Available

Concepts
  Functional vs organizational correctness
  Contracts
  Contract admission                ← NEW; SAFETY-CRITICAL. Why a contract can be refused
  Rules and the verdict
  Breaches
  Conformance vs enforcement        ← NEW. is_pass() vs is_enforced()
  Enforcement postures
  Determinism — and why it matters
  The six-layer architecture

Guides
  Writing your first contract
  Guarding a function
  Choosing an enforcement posture
  Handling non-dict outputs
  Async and concurrency
  Multi-tenant setup
  Offline / air-gapped operation
  Testing your contracts            ← the safety guide; see Stage 4
  When a contract is refused        ← NEW. Reading admission errors; the remediation per code
  Troubleshooting

Reference
  Contract schema vocabulary        ← SAFETY-CRITICAL
  Contract admission codes          ← NEW; SAFETY-CRITICAL. The seven codes, each with a fix
  Configuration (all 48 fields)
  Public API
  Exceptions
  Degraded reasons                  ← NEW. The six DegradedReason values
  Enforcement × guard-mode matrix
  Limits and bounds

Integrations
  LangChain                         Available
  MCP                               Planned — Phase B
  CLI / CI                          Planned — Phase A

Architecture
  Overview
  The six layers
  Ports and adapters
  Control flows
  Failure behaviour
  Invariants and guarantees

Roadmap
  What exists today
  Phases A–F
  Planned: history and evidence
  Planned: multi-agent normalization
  Planned: Business Policy DSL
```

**Verify:** every sidebar link resolves; no orphan pages; status badges present and correct against §15.

**Report:** the tree, and any page you believe should be added or removed, with reasoning.

---

# STAGE 3 — RUNNABLE EXAMPLES (do this before writing prose)

**Goal:** every code sample in the docs is a real file that CI executes. This is the property that makes
these docs incapable of silently rotting, and it is worth the effort.

1. Create `examples/` with, at minimum: `quickstart_pass`, `quickstart_breach`, `enforcement_postures`,
   `guard_modes`, `non_dict_output`, `async_usage`, `offline_standalone`, plus these five, which
   replace the v1 `silently_unenforced` example:

   | Example | Demonstrates |
   |---|---|
   | `admission_refused` | Each of the seven `ContractAdmissionCode` values, loaded **through the production loader**, showing the ERROR line and the code |
   | `admission_capability` | The *same* `minLength` contract refused under default configuration and **admitted** with `CONGINE_SEMANTIC_VALIDATION=true` — the clearest proof that admission judges capability, not a flag |
   | `admission_bypass` | The one live false-safety path (D17): the same contract written via a direct `schema_storage.put()`, then validated — it returns `pass` on output that enforces nothing. **This is the site's most important example** |
   | `enforced_vs_pass` | All three states of `is_enforced()` × `is_pass()`, including a degraded result with `status="fail"` and zero breaches |
   | `nullable_union` | `{"type": ["string","null"]}` **working correctly** — string, `None` and integer. Written as ordinary usage, *not* as a warning |

2. **Run every one.** Capture exact output verbatim.
3. Add a CI job that executes all examples against the SDK and fails if any breaks.
4. Build a Starlight mechanism that embeds an example file (or a named region of it) into a page, so
   documented code and executed code are literally the same bytes.
5. Where an example *should* fail (a breach), capture and display the real breach output.

**If an example does not work, that is a finding — report it. Do not adjust the example to look good.**

**Report:** each example, its verified output, the embed mechanism, and anything that failed.

---

# STAGE 4 — THE SAFETY-CRITICAL PAGES (write these first)

**Goal:** the pages where being wrong actively harms users. They are written before everything else
because they matter most and because later pages link into them.

**4.1 `Reference / Contract schema vocabulary`** — still the most important reference page.
- The **exact eight keywords** the rule engine reads (§13.1). Enumerate.
- **The complete table of keywords not enforced by default** (§13.2) — `minLength`, `maxLength`,
  `format`, `const`, `additionalProperties`, `items`, `allOf`, `anyOf`, `oneOf`, `$ref`,
  `multipleOf`, `exclusiveMinimum`, `exclusiveMaximum`, `minItems`, `maxItems`, `uniqueItems`,
  `patternProperties`, `not`, and every other. For each, **three** columns now, not two: enforced by
  the rule engine? · enforced under semantic validation? · **what happens if you use it anyway**
  (refused at load under default configuration; admitted when an evaluator that enforces it is
  wired). Use the `admission_capability` example.
- **Nullable fields: `{"type": ["string","null"]}` is correct and enforced.** Document it as ordinary
  usage with the `nullable_union` example. **Do not warn about it** — this was a defect (D18), it was
  fixed in `49a2f93`, and the v1 version of this page told users to avoid it. The one caveat that
  *is* real: every member must be a recognised type name, because a union containing an unrecognised
  name would match everything — which is why that case is refused at load.
- The dot-notation asymmetry: supported in `required`, **refused** in `properties` keys.
- Rule-by-rule semantics with edge cases: null handling, bool-is-not-a-number, regex anchoring (full
  match, not partial), length caps failing closed. Note that RE2 supports neither backreferences nor
  lookaround, and that a pattern using either is refused at load rather than breaching at runtime.
- A pre-flight checklist: "before you ship a contract, verify…".

**4.2 `Reference / Contract admission codes` — the new most important page on the site.**
- What admission is and *when* it runs: at load, before a contract can become active policy (§13.8).
- **The seven codes**, each as its own section: what triggers it, the exact ERROR line a user will
  see, and **the specific fix**. A user hitting `ambiguous_property_path` at 2am needs the remedy,
  not the philosophy.
- `strict` vs `warn`: what `warn` adds (portability advisories for enforceable legacy constructs like
  `null_forbidden`) and — stated plainly — **what it cannot do**. `warn` never admits an invalid or
  unenforceable contract. A reader will assume otherwise; correct that assumption explicitly.
- **What happens to a refused contract**, because this is the operational surprise: the write is
  skipped, not cleared, so a previously admitted version keeps serving. On a **cold cache** the
  contract is absent and every guarded call against it raises `CongineContractNotFoundError`.
  Silent non-enforcement was traded for a loud outage, deliberately — say so.
- **The bypass (D17), unsoftened.** A direct `schema_storage.put()` skips admission entirely. Show
  the `admission_bypass` example output: a `pass` on a contract enforcing nothing. Tell the reader
  what to do about it — call the public `admit_contract(...)` before writing. **This is the warning
  that replaces D18 and it must not be buried.**

**4.3 `Concepts / Conformance vs enforcement`** — short, and disproportionately important.
- `is_pass()` answers *did the output conform?*; `is_enforced()` answers *did we actually check?*
- The three states, as a table. The dangerous one is `not is_enforced()`: `status="fail"` with
  **zero breaches**, so a caller reading only `is_pass()` cannot tell a genuine violation from a
  validator that never ran.
- The six `DegradedReason` values, and why `timeout` ("we evaluated too slowly") and `load_shed`
  ("we did not evaluate") are deliberately distinct.
- Guidance: treat "not enforced" as *unknown conformance*, never as a pass.

**4.4 `Guides / Testing your contracts`** — how a user proves a contract enforces what they believe,
before relying on it. The practical countermeasure to 4.1 and 4.2. Cover `admit_contract` as
something a user can call directly in their own test suite — it is exported for exactly this.

**4.5 `Concepts / Determinism`** — what it means, what it buys, and what would destroy it. Explains
why no model sits on the verdict path.

**Report:** these five pages in full for review. They are the ones most worth your scrutiny.

---

# STAGE 5 — CORE CONTENT

Write, in this order: **Start here → Concepts → Guides → Reference → Architecture → Integrations →
Roadmap.**

Per-page requirements:
- Opens with what the reader will be able to do or understand afterwards.
- Code samples embedded from `examples/`, never hand-written inline.
- Explanation before instruction — say *why* before *how*.
- Cross-links resolve; every concept links to its reference page.
- Status badge accurate.
- Technical claims cite `ARCHITECTURE_CURRENT §n` where the reader would want depth.

Specific pages that need care:
- **Installation** — **check the current publication state before writing this page; do not inherit
  an answer from this prompt.** At the time of writing the SDK was not on PyPI, but that is exactly
  the kind of fact that goes stale. Verify (search PyPI for the distribution name, check
  `pyproject.toml`, check for a release workflow or published tags), then document what is actually
  true. If it is published, give the real `pip install` / `uv add` command; if it is not, document
  install *from source* honestly and note PyPI as forthcoming. Either way, **run the command you
  write** — do not ship an install command that fails.
- **Quickstart** — the offline/standalone path, no control plane, five minutes end to end, ending in a
  passing validation *and* a deliberate breach so the reader sees both.
- **Enforcement × guard-mode matrix** — a table, not prose. Include that a degraded (timeout or
  load-shed) result **raises** under strict mode; this surprises everyone.
- **Configuration** — every field, **derived by measurement** rather than copied from this prompt:
  enumerate `dataclasses.fields(CongineConfig)` at HEAD and cross-check against the README table
  (which `tests/unit/test_readme_config_table.py` keeps honest). It was 48 fields at the P1 CLOSED
  commit; treat that as a checksum, not as the source. Three things need calling out on this page:
  - `region` is **metadata** — it selects no endpoint, and setting it without `CONGINE_BASE_URL`
    raises. (Do not describe it as "accepted but unread"; that was debt D1 and it is closed.)
  - **Malformed values now raise rather than defaulting.** `CONGINE_TELEMETRY_ENABLED=TRUE!` used to
    silently mean `false`; an unrecognised `CONGINE_CONTRACT_SOURCE` used to silently mean HTTP; an
    empty `CONGINE_LOCAL_CONTRACTS_DIR` used to select a broken standalone mode. Anyone upgrading
    needs this, and it belongs on the page rather than only in a changelog.
  - **A directly constructed `CongineConfig` is validated exactly like an environment-derived one.**
    Worth a sentence, because the previous behaviour — construction skipping validation entirely —
    is what a reader coming from an older version will assume.
- **Architecture pages** — summarise and link to `ARCHITECTURE_CURRENT.md`; do not duplicate it.
  Present the six layers as **L0 Shared Kernel · L1 Ports · L2 Domain · L3 Use Cases ·
  L4 Infrastructure · L5 Adapters**, and get these four right, because they are the ones most likely
  to be written wrong from older sources:
  - **Link to and reproduce the explicit dependency matrix.** Do **not** write that "L4 may import
    any lower-numbered layer" or that "dependencies point inward" without immediately qualifying it:
    `L4 → L2` and `L4 → L3` are **forbidden**, and infrastructure reaches policy through ports.
  - **The canonical value contracts live in L0** (`congine_core/models.py`), not in
    `domain/models.py`, which is a compatibility re-export. L2 owns deterministic judgment.
  - **`TYPE_CHECKING` imports are enforced** under the same matrix — no exemptions, no allowlist.
  - **Enumerate ports from `congine_core.ports.__all__`**, never from a remembered count, and never
    omit `ISyncRunner`. Mention that the architecture rule is machine-checked in CI, which is a
    genuinely differentiating thing to be able to say.
- **Integrations / MCP** — describes intent and the attachment point (§15.1), clearly `Planned — Phase B`.
  **No setup instructions.**

**Report per session:** pages completed, and any place the SDK's actual behaviour made a page awkward to
write — that is usually a real usability defect worth fixing in the SDK.

---

# STAGE 6 — POLISH AND VERIFY

1. **Build clean.** No warnings, no broken links (run a link checker), no missing images.
2. **Search** returns sensible results for: contract, breach, minLength, union type, timeout,
   **load shed**, **admission**, **refused**, **is_enforced**, tenant, enforcement, offline.
3. **Responsive** at 375px, 768px, 1440px. Code blocks scroll rather than overflow.
4. **Accessibility:** headings ordered, contrast passes, keyboard navigation works, code blocks labelled.
5. **Lighthouse ≥ 95** on performance and accessibility for home, quickstart and the vocabulary page.
6. **The five-minute test:** follow the quickstart yourself, from a clean directory, exactly as written.
   Time it. If it exceeds five minutes or requires a step not on the page, fix the page.
7. **The honesty audit, both directions:**
   - **Understating what exists** — grep every page for claims about the eight unbuilt capabilities.
     Confirm each is badged `Planned` and offers no instructions.
   - **Overstating what is broken** — grep every page for `D18`, `union`, `silently ignored`,
     `dead configurable`, `46 fields`, `accepted but unread`, `ValidationTimer`, `stdlib re`,
     `inward only`, `seven ports`, and any test count other than the current one. Every hit must be
     checked against
     `ARCHITECTURE_CURRENT.md` §16's reconciliation table. A page that warns about a fixed defect is
     as wrong as one that
     documents a feature that does not exist, and it is more embarrassing, because it tells a
     developer to avoid something that works.
8. Screenshot the key pages in both themes and confirm they render correctly.

**Report:** the audit results, the timed quickstart, and any remaining known issue.

---

# WHAT NOT TO DO

- Do not document unbuilt features as usable.
- Do not hand-write code samples that are not in `examples/` and executed.
- Do not soften the vocabulary, admission-code, or D17-bypass warnings.
- **Do not warn about the union-type defect.** It is fixed. Document unions as the correct way to
  declare a nullable field.
- Do not duplicate `ARCHITECTURE_CURRENT.md` — link to it.
- Do not modify the SDK. If you find a bug, report it.
- Do not run multiple stages in one session.
- Do not add marketing copy.

# FINAL REPORT

Site URL/command; stages complete; example count and CI status; the timed quickstart result; the honesty
audit result; SDK usability defects discovered; anything you could not verify.

```text
=== END PROMPT W1 ===
```

---

## After each stage — your checklist

- [ ] **Stage 3:** confirm the `admission_bypass` example runs and shows a `pass` on a contract that
      enforces nothing. That single example is the empirical spine of the most important page on the
      site — it is the one live false-safety path, and a site that cannot demonstrate its own
      remaining gap is not trustworthy about the rest.
- [ ] **Stage 3:** confirm `nullable_union` runs clean, and that nothing anywhere calls it a defect.
- [ ] **Stage 4:** read the vocabulary and admission-codes pages as if you were a new user. Two
      questions: *could I still ship a contract I wrongly believe is enforced?* and *if my contract
      is refused at 2am, does this page tell me what to change?* If either answer is bad, the pages
      are not done.
- [ ] **Stage 6:** actually do the timed quickstart yourself. Do not take the report's word for it.
- [ ] **Stage 6:** run the honesty audit in **both** directions. The reverse direction — warning
      about closed defects — is the one this batch is most likely to fail, because the prompts it
      inherited from were written before the fixes landed.
