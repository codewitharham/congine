# WEB ARCHITECTURE & TOOLING — THE TWO SITES

Read before running `PROMPT_W1` or `PROMPT_W2`. Answers your structural question (three repos or one?),
selects the stack, settles Claude Design versus Claude Code, and states the rule that keeps both sites
honest.

---

## 1. YOUR QUESTION: THREE PROJECT STRUCTURES?

**No. One monorepo.** Polyglot monorepos are ordinary and this is materially better than three
repositories.

> **CORRECTED 2026-08-22 — the Node toolchain already exists, and it is not pnpm.**
> When this file was drafted, the Node side was a proposal. The repository now has an established
> and CI-exercised topology:
>
> | Concern | Tool |
> |---|---|
> | Python workspace and dependencies | **uv** |
> | Node dependency installation | **npm** (`package.json`, `package-lock.json` at the root) |
> | Project and task orchestration, both languages | **Nx** (`nx.json` at the root) |
>
> **Therefore:** do **not** introduce pnpm, do **not** create `pnpm-workspace.yaml`, and do **not**
> overwrite or regenerate the root `package.json`. New web projects join the existing Nx/npm
> monorepo as additional **Nx projects**, each with its own `project.json` declaring its targets.
> Verified commands: `npm ci`, `npm exec nx -- show projects`,
> `npm exec nx -- run <project>:<target>`. Every `pnpm ...` command later in this file is superseded
> by its npm/Nx equivalent.

**Why one repo:**
- The docs site must stay truthful about the SDK. In one repo, an SDK change and its documentation
  change land in the same commit and the same review. Across repos they drift within weeks — and drift
  in *your* documentation is the exact failure your product exists to prevent.
- Examples in the docs can be **executed against the real SDK in CI**. This is the single highest-value
  property available to you and it is impossible across repos.
- One CI, one dependency graph, one place to look.

**Why not one giant app:** the sites are genuinely separate deployables with different lifecycles.
Workspaces, not folders.

### The layout

```
congine/                                  ← existing monorepo root
├── pyproject.toml                        ← EXISTS NOW: uv workspace root
├── uv.lock                               ← EXISTS NOW
├── package.json                          ← EXISTS NOW: npm root (do not overwrite)
├── package-lock.json                     ← EXISTS NOW
├── nx.json                               ← EXISTS NOW: Nx orchestration
├── libs/
│   └── congine-sdk/                      ← EXISTS NOW: the engine. UNTOUCHED by this work.
│       ├── project.json                  ← EXISTS NOW: lint · typecheck · architecture · examples · test
│       ├── tools/                        ← EXISTS NOW: architecture gate + P0 evidence harnesses
│       └── examples/LangChain/           ← EXISTS NOW: CI-executed offline example
│
├── apps/
│   ├── docs/                             ← PLANNED W1: Astro Starlight documentation site
│   └── control-plane/                    ← PLANNED W2: Next.js prototype
│       └── (api/ added later)            ← PLANNED Phase C+: NestJS, when there is real data
│
├── packages/
│   ├── design-tokens/                    ← PLANNED W1: shared colour, type, spacing
│   └── ui/                               ← PLANNED W2: shared React components
│
└── docs/                                 ← EXISTS NOW: architecture, adr, _suite (markdown, not the site)
```

**Read the annotations literally.** `EXISTS NOW` is present at the P1 CLOSED commit; `PLANNED W1` /
`PLANNED W2` / `PLANNED Phase C+` are not built. Do not describe a planned app or package as
existing.

Each new app or package is registered as an Nx project (its own `project.json`) rather than through
a pnpm workspace file. There is no `pnpm-workspace.yaml` and none should be created.

**Two rules that keep this clean:**
1. **Nothing under `apps/` or `packages/` may import from `libs/congine-sdk` at build time.** The sites
   are consumers, not extensions. The SDK stays Python-only and independently publishable.
2. **Runnable, CI-executed examples are the bridge.** The principle is what matters, not the
   location: **documentation code samples must come from source-controlled runnable examples that
   CI/Nx executes.** When the SDK changes and an example breaks, CI fails — the docs cannot silently
   rot.

   **This already exists and should be reused, not duplicated.** `libs/congine-sdk/examples/LangChain/`
   is executed by the Nx target `congine-sdk:examples` (`npm exec nx -- run congine-sdk:examples`),
   which runs the real offline guard path in CI. W1 may add a dedicated docs-examples project if it
   genuinely needs samples the SDK example does not cover — but **do not copy the working SDK example
   into a second source of truth** without a reason, because two copies of an example is exactly the
   drift this rule exists to prevent.

> **This property is now load-bearing rather than nice-to-have.** The P0 pass introduced eight
> deliberate breaking changes (see `docs/_suite/hardening/P0_COMPLETION_REPORT.md`) — malformed booleans raise, invalid
> `contract_source` raises, empty directory paths raise, `region` without a base URL raises, unsafe
> contracts are refused, saturation reports `load_shed` rather than `timeout`. **Any documentation
> example written before that pass would break on at least one of them.** An executed-in-CI example
> would have caught every one at the moment it landed. Treat the CI job as the mechanism that makes
> this class of drift impossible, not as a testing nicety — it is the same argument the SDK makes
> about contracts, applied to its own documentation.

---

## 2. STACK SELECTION

### Docs site — **Astro Starlight**

| Candidate | Verdict |
|---|---|
| **Astro Starlight** | **Chosen.** Purpose-built for docs; ships almost no JS; excellent MDX, code groups, tabs, file trees, built-in search; framework-agnostic islands if interactivity is needed later. |
| Docusaurus | Mature and React-native, but heavier and its versioning machinery is overhead you do not yet need. |
| Nextra | Good, and shares React with the control plane — the runner-up. Choose it instead **if** you want one React toolchain across both sites. |
| VitePress | Excellent but Vue-centric; pulls you away from the React control plane. |
| Hand-built | No. You would spend the effort on navigation, search and code highlighting instead of content. |

Starlight gives you a professional docs site on day one and lets the work go into what actually matters:
the writing and the runnable examples.

### Control plane prototype — **Next.js + Tailwind + shadcn/ui + Recharts**

React, because the control plane is genuinely interactive and you will later want a NestJS API behind
it. shadcn/ui gives you owned, editable components rather than a fought-with component library.
Recharts covers the telemetry visualisations.

**The mock-data seam is the critical design element** — see §4.

### Later: the real control plane API — **NestJS + PostgreSQL**

Matches your stated intent. Build it **after Phase C**, when the durable event store exists and there
is real data. The prototype's data layer is designed so this is a swap, not a rewrite.

---

## 3. CLAUDE DESIGN OR CLAUDE CODE?

**Claude Code for both. Claude Design optionally, for one narrow job.**

| | Claude Design | Claude Code |
|---|---|---|
| Produces | Designs, screens, visual direction | Running applications |
| Sees your codebase | No | **Yes** |
| Can verify its output | No | **Yes — runs it, screenshots it, fixes it** |
| Right for | Exploring visual language | Building sites, docs, data-driven UI |

The docs site is 90% content correctness and 10% visual design — Claude Code, decisively. The control
plane has real visual-design weight, but it is still an application; a design that cannot be run cannot
be validated.

**The one legitimate use of Claude Design:** before running W2, ask it for **visual direction only** —
colour system, typography scale, and two or three key screens as static compositions, for the control
plane alone. One surface, one stage, no IA, no journeys, no prototype. That is the size of brief it
handles well. Then hand the direction to Claude Code as an input.

This is the division the previous attempt collapsed: **Design explores, Code builds.**

---

## 4. THE HONESTY RULE (non-negotiable, both sites)

`ARCHITECTURE_CURRENT.md` §15 confirms eight capabilities **do not exist**: MCP server, CLI, persistent
event store, history queries, correction hints, architecture graph, agent adapters, adaptive routing.
§1 is blunter still: *"There is no server, no database, no CLI, no persistence."*

> **Still true at `6345a1e`** — re-verified 2026-08-17. None of the eight was built by `49a2f93` or
> `6345a1e`; both were hardening passes over the existing engine. The absence list is unchanged.

So:

**The docs site must not document a product that does not exist.** No MCP setup guide, no CLI reference,
no history API. Those pages exist as clearly-marked **Roadmap** entries describing intent, never as
instructions. A developer who follows an install guide for a nonexistent feature never returns.

**Every control plane screen is mock data, and must say so.** A persistent, visible `PROTOTYPE — SAMPLE
DATA` indicator. Not a footnote. Not removable by a config flag. If you demo this and someone believes
the numbers are real, you have created a problem you cannot walk back.

**Both sites carry a status vocabulary, used identically:**

| Badge | Meaning |
|---|---|
| `Available` | Implemented and usable today |
| `Partial` | Exists with documented limitations |
| `Planned — Phase X` | Designed, not built |
| `Prototype` | Shown for design purposes; not backed by a real system |

This is not timidity. It is the same discipline as the product: **no silent non-enforcement.** A
governance company whose own surfaces overstate their status has undermined the only thing it sells.

### 4.1 The second honesty rule — do not warn about a defect that is fixed

Added 2026-08-17, and it cuts the opposite way from the rule above.

The v1 batch instructed both sites to treat the **union-type defect (D18)** as the single most
important warning to surface: `{"type": ["string","null"]}` caused silent permanent degradation of
every validation against that contract. **That defect is fixed** (`49a2f93`) — unions are a
first-class, enforced spelling. A docs site that still warns about it would be telling developers to
avoid the correct way to write a nullable field.

Overstating a *defect* is the same failure as overstating a *capability*: both are a surface that
does not match the system. The current safety story, which both sites must carry instead:

- **Contracts are admitted before they become active policy** (`ARCHITECTURE_CURRENT.md` §13.8).
  Seven machine-facing refusal codes. A contract CONGINE cannot interpret is refused at load, not
  quietly accepted.
- **The consequence is a real trade and must be stated**: a refused contract is absent, so on a cold
  cache every guarded call against it raises. Silent non-enforcement was traded for a loud outage,
  deliberately.
- **Admission runs on the loader path only** (debt D17). A direct `schema_storage.put()` bypasses it.
  This is the live warning that replaces D18.
- **`is_pass()` does not tell you whether the policy was evaluated** — callers ask `is_enforced()`
  first (§11.2). This one belongs on both sites, because it is the distinction a dashboard is most
  likely to get wrong.

**The operating rule for both prompts:** before writing any warning, check it against
`ARCHITECTURE_CURRENT.md` §16's reconciliation table, which gives each item a verified status
(resolved / open / superseded / deferred) rather than a headline count. Most recorded debts are
closed, and a surface that
warns about closed ones reads as stale rather than careful.

---

## 5. SEQUENCE

```
W1 — Docs site        (real, ships value, establishes design tokens)
        │
        ▼
W2 — Control plane    (prototype, inherits tokens, honest mock data)
        │
        ▼
[after Phase C]  NestJS API + Postgres → swap the data layer, prototype becomes product
```

**W1 first**, for three reasons: it documents things that exist so it can be correct today; it produces
the shared design tokens W2 inherits; and it forces the five-minute-install test, which will surface
real gaps in the SDK's usability that no dashboard would reveal.

---

## 6. SETUP COMMANDS (run once, before W1)

> **Rewritten 2026-08-22.** The original block bootstrapped a pnpm workspace and **overwrote the root
> `package.json`**. Both are now wrong and destructive: the workspace already exists on npm + Nx, and
> that `package.json` is in use. The steps below are additive.

```bash
# from the monorepo root — install the existing workspace
npm ci
uv sync --all-extras

# confirm what is already registered before adding anything
npm exec nx -- show projects
npm exec nx -- show project congine-sdk --json
```

Then create each new app or package **as an Nx project**, letting the relevant Nx generator write its
`project.json` and register it. Do not hand-edit the root `package.json` workspace configuration, and
do not add `pnpm-workspace.yaml`.

Task commands follow the existing convention already used for the SDK:

```bash
npm exec nx -- run <project>:<target>      # e.g. congine-sdk:test
npm exec nx -- run-many -t build
```

**Verify before you quote.** The SDK's targets are `lint`, `typecheck`, `architecture`, `examples`
and `test`; targets for a not-yet-created docs or control-plane project do not exist until that
project does. Read `project.json` rather than assuming a target name, and never document a
`pnpm dev:docs`-style script — no such script exists.

Leave scaffolding of the individual apps to the prompts — they pin versions and verify the result.

---

## 7. WHAT SUCCESS LOOKS LIKE

**Docs site:** a developer who has never seen Congine lands on it, follows the quickstart, and has a
passing validation and a deliberately failing one inside five minutes — without asking you anything.

**Control plane prototype:** a stakeholder clicks through it and understands what governed AI-assisted
development would feel like, while never once believing the data is real.

Those two sentences are the acceptance tests. Everything in the prompts serves them.
