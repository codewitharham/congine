# PROMPT W2 — THE CONTROL PLANE PROTOTYPE

## How to use

**Where:** Claude Code, at the monorepo root. **Run after W1** (it inherits the design tokens).

**Attach:** `WEB_ARCHITECTURE_AND_TOOLING.md` (binding). Optionally, a visual direction from Claude
Design if you chose to explore one first. Reads from repo: `ARCHITECTURE_CURRENT.md`,
`packages/design-tokens`.

**Produces:** `apps/control-plane/` (Next.js), `packages/ui/`.

**Run one stage per session.** Seven stages.

---

```text
=== BEGIN PROMPT W2 ===
```

# ROLE

You are a staff product engineer building the **Congine Control Plane prototype** — the governance
surface an organization would use to see and steer how AI-assisted development is governed across its
teams.

# READ THIS BEFORE ANYTHING ELSE

**You are building a prototype against a backend that does not exist.**

`ARCHITECTURE_CURRENT.md` §1: *"It is a library, not a service. There is no server, no database, no
CLI, no persistence. Every piece of state … is process-local."* §15 confirms the durable event store,
history queries, architecture graph, agent adapters and MCP server are all absent.

Therefore **every number on every screen is fabricated**, and three things follow, all mandatory:

1. **A persistent, always-visible `PROTOTYPE — SAMPLE DATA` indicator.** In the app shell, on every
   route, not dismissible, not behind a flag. If a viewer can forget the data is synthetic, the
   prototype has become a liability.
2. **The mock data layer sits behind a clean seam** (§Stage 2). When the real API arrives after Phase C,
   swapping it must be a change of implementation, never a rewrite of the UI.
3. **The mock data must be realistic, not flattering.** Real systems have breaches, degraded verdicts,
   dropped telemetry, tenants with poor contract coverage and agents that perform badly. A dashboard
   where everything is green teaches nothing and convinces no one.

> **Revised 2026-08-17 against `6345a1e`.** Two commits landed after this prompt was drafted:
> `49a2f93` and `6345a1e` (the P0 Trust-Critical Hardening pass). Neither builds any of the eight
> absent capabilities — this is still a prototype against a backend that does not exist — but
> `6345a1e` **changed the domain model this prototype is modelling**, in three ways that matter more
> here than anywhere else in the batch:
>
> 1. **A validation result now has two independent axes**, not one: *did it conform?* (`is_pass()`)
>    and *was it actually evaluated?* (`is_enforced()`). A dashboard that renders only pass/fail is
>    modelling the pre-P0 system and will mislead every viewer.
> 2. **Contracts can be refused before they become active policy** (contract admission, §13.8). That
>    is a first-class lifecycle state a contract registry must show — a contract can now be
>    *published but not active*.
> 3. **Load shed is distinct from timeout.** Two different operational problems that used to look
>    identical; a telemetry view that conflates them tells an operator to investigate a slow contract
>    when the real answer is to scale.
>
> Read `ARCHITECTURE_CURRENT.md`'s current-state header block, §11 and §13 before Stage 2. Stage 2 is
> the stage this affects most, because these distinctions belong in the **domain types**, not in the UI.
>
> **Revised again 2026-08-22, at P1 closure (`b482bc4`).** P1 was a structural hardening pass. It
> **confirms rather than changes this prompt's premise**: there is still no durable event store, no
> authoritative history API and no control-plane service backend, so this remains a prototype against
> a backend that does not exist and the `PROTOTYPE — SAMPLE DATA` indicator stays exactly as
> specified. Two corrections for Stage 2:
>
> - The SDK's canonical value contracts now live in **L0 `congine_core/models.py`**, not in
>   "L2 domain models". Refer to them correctly, and remember the TypeScript types are
>   *representations derived from public/event semantics* — never shared or imported Python classes.
> - Telemetry remains explicitly **non-durable** (queue-full, retry-exhaustion, breaker-OPEN and
>   process death all drop events apart from a counter). Any evidence/history field in the type layer
>   is **`PLANNED`**, and must be labelled so.

# TIME AND EFFORT

**TAKE AS MUCH TIME AND AS MANY SESSIONS AS YOU NEED. THIS IS EXPLICITLY AUTHORIZED AND EXPECTED. THERE
IS NO TIME PRESSURE.**

One stage per session. Verify each before proceeding — build it, run it, screenshot it, look at it. The
previous attempt failed by collapsing the whole design pipeline into one pass; the staging exists to
prevent exactly that. Checkpoint to `apps/control-plane/PROGRESS.md` if context runs low.

# WHAT THIS IS FOR

A stakeholder — an engineering leader, a compliance officer, an investor — clicks through this and
understands what governed AI-assisted development *feels* like, while never once believing the numbers
are real. That is the acceptance test.

---

# STAGE 1 — SCAFFOLD AND SHELL

1. Scaffold Next.js (App Router, TypeScript) into `apps/control-plane` as `@congine/control-plane`,
   **as an Nx project** in the existing npm + Nx workspace. Add Tailwind, shadcn/ui, Recharts. Pin
   versions. **Do not introduce pnpm, do not create `pnpm-workspace.yaml`, and do not overwrite the
   root `package.json`** — see `WEB_ARCHITECTURE_AND_TOOLING.md` §1 and §6. Install with `npm ci`,
   give the project a `project.json`, and confirm dev and build both work via
   `npm exec nx -- run control-plane:<target>`.
2. Consume `packages/design-tokens` — **the same tokens the docs site uses.** The two surfaces must
   look like one product. Extend, do not replace: the semantic `pass` / `breach` / `degraded` /
   `blocked` colours are already defined and are used heavily here.
3. Build the app shell: sidebar navigation, top bar with organization and tenant switchers, user menu,
   and the **permanent prototype banner**.
4. Create `packages/ui` for components shared between shell and features.
5. Verify: dev server runs, build passes, both themes render, responsive at 1280px and 1920px (this is
   a desktop application — mobile is not a target beyond not being broken).

**Report:** the shell, the token inheritance, and a description of what it looks like.

---

# STAGE 2 — THE DATA SEAM (the most important architectural decision here)

**Goal:** make the eventual swap to a real API mechanical.

1. Define the **view/domain types** first, derived from the SDK's canonical value contracts —
   `ARCHITECTURE_CURRENT.md` §11, which since P1 live in **L0 `congine_core/models.py`**, not in
   "L2 domain models" — extended with the fields the durable event store will carry (§15):
   validation events, verdicts, breaches, contracts and versions, tenants, agents, projects,
   enforcement postures, telemetry aggregates.

   **These TypeScript types are *representations derived from* the SDK's public and event semantics.**
   They are not, and must never be described as, shared or imported Python classes. The web
   application does not import SDK internals, and nothing in `apps/` or `packages/` may depend on
   `libs/congine-sdk` at build time. When the SDK's public semantics change, these types are updated
   deliberately — that seam is the point.

   **Label the two tiers distinctly in the type definitions themselves.** Fields that mirror what the
   SDK produces today (status, breaches, degraded reason, duration, contract id/version) are one
   tier. Fields the durable event store *will* carry — tenant, agent, project, contract version
   identity, evidence and history records — are **`PLANNED`** and must be commented as such. Do not
   let a planned field read as something the current SDK already persists: today telemetry is
   explicitly **not durable**, and inventing persistence in the type layer is how a prototype starts
   lying.

   **Four modelling requirements, all from `6345a1e`. Get these into the types, not the components.**

   - **A verdict has two axes.** Model `enforced: boolean` alongside `status: "pass" | "fail"`, not a
     single tri-state. The three legitimate combinations are *evaluated + conforming*, *evaluated +
     violated*, and **not evaluated** — and the third carries `status="fail"` with **zero breaches**,
     which is exactly the shape that misleads a naive renderer into showing a violation that never
     happened. Give the semantic colour set a fourth member for it: `pass` / `breach` / **`unenforced`**
     / `blocked`, distinct from `degraded`.
   - **`degradedReason` is a closed enum of six**, not a free string:
     `timeout` · `load_shed` · `resource_error` · `internal_error` · `invalid_payload` ·
     `invalid_contract` (§11.2). `timeout` and `load_shed` must never be aggregated into one bucket —
     they are different operational problems with different responses.
   - **A contract has an admission state.** `admitted` / `refused`, with a refusal carrying its
     machine-facing `ContractAdmissionCode` (one of seven), the `path`, and the version that was
     refused. A refused contract is *published but not active*, and the previously admitted version
     keeps serving — the type must be able to express that a registry entry's **latest** version and
     its **active** version differ.
   - **Admission health is a metric.** `contractsRejectedTotal` and `lastAdmissionFailure` are
     already reported by the real `ServiceContainer.health()`, so they are not speculative. They
     answer a question an operator genuinely has: *is the old policy still active because the control
     plane is unreachable, or because a new version arrived and was refused?*
2. Define a **repository interface** per domain area — `ValidationEventRepository`,
   `ContractRepository`, `TenantRepository`, `AgentRepository`, `TelemetryRepository`. Methods
   express *what the UI needs*, not what a mock can conveniently supply.
3. Implement `MockValidationEventRepository` etc., seeded from a deterministic generator so the data is
   stable across reloads (a demo whose numbers change on refresh is not credible).
4. **The UI may only ever touch the interfaces.** No component imports mock data directly. Add a lint
   rule or CI check enforcing this — it is the seam's only real protection.
5. Simulate realistic latency and, occasionally, failure — so loading and error states are designed
   rather than forgotten.
6. Write `apps/control-plane/README.md` documenting exactly what a real implementation must provide.
   This is the specification the NestJS API will later satisfy.

**The seed data must include:** several tenants with genuinely different maturity; contracts in all
three postures; a realistic breach rate; some degraded verdicts from timeouts; at least one tenant with
poor contract coverage; several agents with measurably different performance; a period where something
went wrong.

**And, so the new distinctions are visible rather than theoretical:**

- **Both degradation causes, separately.** A period of `timeout` degradations (a slow contract) and a
  distinct burst of `load_shed` (a saturation incident). These should look different on the
  telemetry views, because they *are* different — and a viewer who cannot tell them apart is looking
  at the exact conflation P0-06 removed.
- **At least one refused contract**, ideally two with different codes (`unsupported_keyword` and
  `ambiguous_property_path` are the most instructive). Show a tenant whose *latest* contract version
  was refused while an **older admitted version is still serving** — that is the single most
  operationally important state in the whole model, and it is invisible unless the data contains it.
- **A tenant whose refusal went unnoticed**, with its `contractsRejectedTotal` climbing across the
  window. This is what the admission-health metric exists to surface.
- **A non-trivial fraction of unenforced verdicts** — enough that "% of validations actually
  enforced" is a meaningful tile rather than a constant 100%.

**Report:** the type definitions, the interfaces, and the seed data profile.

---

# STAGE 3 — INFORMATION ARCHITECTURE AND ROUTES

Stub every route with layout and navigation, no real content yet — the shape must be reviewable before
the screens are built.

```
/                          Organization overview
/governance
  /contracts               Contract registry
  /contracts/[id]          Contract detail: versions, posture, violation history
  /contracts/[id]/simulate Policy simulation (what would this contract have caught?)
  /evidence                Validation event stream
  /evidence/[id]           Single event: verdict, breaches, replay
/teams
  /tenants                 Tenant list — coverage, posture, health
  /tenants/[id]            Tenant workspace
/agents
  /                        Agent inventory and comparison
  /[id]                    Agent detail: performance by contract type
/telemetry
  /enforcement             Postures, blocks, overrides
  /convergence             Retries-to-converge
  /economics               Token volume and savings
  /correctness             Violations reaching main
/architecture              Architecture graph            [Planned — Phase E]
/settings
  /organization
  /members
  /integrations            MCP, CLI                      [Planned — Phase A/B]
```

Routes for unbuilt capabilities render an honest **"Planned — Phase X"** state describing what will live
there. **They do not render fake versions of features that do not even have a design.**

Define the **role-based views** as a shell-level concept: Engineering lead, Compliance, Platform,
Executive. Each is a different default landing view and emphasis over the same data — not four separate
applications.

**Report:** the route tree and the role-view model.

---

# STAGE 4 — THE THREE SCREENS THAT MATTER

Build these three to full fidelity before anything else. They carry the product's argument.

**4.1 The Evidence Stream and Event Detail (`/governance/evidence`)**
The proof that governance happened. A live-feeling stream of validation events — contract, verdict,
tenant, agent, duration, posture. Filterable. The detail view shows the full verdict: every breach with
rule, field and message; the contract version evaluated against; timing; the enforcement decision and
whether it blocked. Include a **replay** affordance — the same input against the same contract version
producing the same verdict. **This screen is where determinism becomes visible**, and it is the single
most convincing thing in the product.

**Render the enforced axis as a first-class distinction, not a subtitle.** An unenforced result must
be visually distinct from both a pass and a breach — it is neither. A row showing "fail, 0 breaches"
with no further explanation is the exact ambiguity `is_enforced()` was added to remove, and
reproducing it here would be a self-inflicted wound. Filtering by `degradedReason` (all six values)
belongs in the stream controls, and `timeout` vs `load_shed` must be separately selectable.

**4.2 The Contract Workspace (`/governance/contracts`)**
Where the standard lives. Registry with posture, coverage, version, violation frequency. Detail view
with version history and the lifecycle stage. **Include the posture ladder as a first-class control** —
observational → permissive → strict — because graduated adoption is the mechanism that makes this
adoptable at all. Include a simulation view: *"if this contract moved to strict, N changes in the last
30 days would have been blocked"* — this is what makes a compliance officer trust the tool.

**Add admission as a lifecycle stage.** A contract version is `admitted` or `refused`, and the
registry must show when the **latest** version and the **active** version diverge — a refused update
leaves the previous version serving, which is good behaviour and terrible if it is invisible. A
refused version shows its `ContractAdmissionCode`, the offending `path`, and the remediation. This is
arguably the most useful screen in the prototype for a platform engineer, because it is the one
question the SDK's logs answer badly.

**4.3 Organization Overview (`/`)**
The answer to "how is my organization being governed?" Contract coverage of critical paths; in-loop
validation rate; violations reaching main; convergence trend; posture distribution; tenants needing
attention. **Every tile links to the evidence behind it** — a governance dashboard whose numbers cannot
be drilled into is a dashboard nobody trusts.

**Two tiles carry the new model and should be prominent:**

- **"% of validations actually enforced."** Not the pass rate — the *enforcement* rate. It is the
  honest headline number for a governance product, and it is the one a viewer will not think to ask
  for.
- **"Contracts refused, not active."** Drills into the contract workspace. A non-zero value means
  policy a team believes is live is not.

Each screen needs: loading state, empty state, error state, and a populated state built from the
realistic seed data.

**Report:** the three screens described in detail, with what you would change on a second pass.

---

# STAGE 5 — THE REMAINING SURFACES

Build out, in this order: tenant workspace → agent views → telemetry views → settings → planned-state
routes.

**Specific guidance:**

- **Tenant workspace** — this is your "management system for each employee/team" requirement. Their
  contracts, their events, their coverage, their agents, their convergence. Scoped, not a filtered copy
  of the org view.
- **Agent inventory** — the multi-agent normalization story made visible. Per-agent success rate by
  contract type, convergence, cost. **Frame it as observed statistics, never as a learned model** —
  that distinction is a product invariant. Mark it `Planned — Phase E` since adapters and profiles do
  not exist.
- **Telemetry views** — four families: enforcement, convergence, economics, correctness. Charts must be
  legible at a glance and drillable. Prefer few, well-chosen charts over a wall of them.
  **In the enforcement family, the degradation breakdown must separate the six `DegradedReason`
  values** — at minimum, `timeout` and `load_shed` must never share a bucket. They prescribe
  opposite responses: one says a contract is slow, the other says the system is saturated. Merging
  them would rebuild in the dashboard the exact ambiguity the SDK removed at the source.
- **Economics view** — the token savings story. Be careful: label the methodology, since these numbers
  will be scrutinised hardest.
- **Planned routes** — a designed, dignified "not yet" state that explains what will be here and in
  which phase. Not an error page.

**Report per session:** screens completed and any that felt thin, with why.

---

# STAGE 6 — INTERACTION AND MOTION

Make it feel like a real product, restrained.

- Real-time *feel* on the evidence stream (poll or simulate a stream through the repository interface —
  never bypass the seam).
- Transitions that aid comprehension, never decorate. Nothing that delays a user.
- Keyboard: command palette, `/` to search, `Esc` to close, arrow navigation in lists.
- Optimistic UI where a real API would allow it, so the interaction model is already right.
- Skeleton loaders matching the eventual content shape.

**Restraint is the instruction.** This is a governance tool for professionals; it should feel precise
and calm. Anything that reads as playful undermines the product's entire claim.

---

# STAGE 7 — VERIFY AND HARDEN

1. **Build clean.** No TypeScript errors, no console errors, no unhandled promise rejections.
2. **Every route renders** in every state: loading, empty, error, populated.
3. **The seam holds** — no component imports mock data directly. Verify mechanically.
4. **The prototype banner is present on every route** and cannot be dismissed.
5. **The honesty audit:** walk every screen and confirm nothing implies a capability that §15 says is
   absent. Every planned surface is badged.
5a. **The fidelity audit** — new, and specific to this revision. Confirm that:
   - no screen renders a verdict as pass/fail alone where the result was **not enforced**;
   - `timeout` and `load_shed` are never aggregated;
   - the contract registry can show a refused latest version with an older version still active;
   - the "% enforced" tile exists and is not pinned at 100%.
   Each of these is a case where a plausible-looking dashboard would misrepresent the engine.
6. **Responsive** at 1280px and 1920px; not broken below.
7. **Accessibility:** keyboard navigation throughout, contrast passes, charts have text alternatives,
   focus visible.
8. **Screenshot every major screen** and review them as a set — do they look like one product, and like
   the docs site?
9. **The stakeholder test:** click through as if you were a compliance officer seeing it for the first
   time. Is the story legible without narration?

**Report:** audit results, screenshot descriptions, known issues, and what the real API must provide
(from the Stage 2 README).

---

# WHAT NOT TO DO

- Do not remove or weaken the prototype indicator.
- Do not let any component touch mock data directly.
- Do not build screens for capabilities that have no design — use the planned state.
- Do not make the seed data uniformly positive.
- **Do not collapse `is_pass()` and `is_enforced()` into one status.** Two axes, always.
- **Do not bucket `timeout` with `load_shed`.**
- Do not build a NestJS backend. **That comes after Phase C, when there is real data.**
- Do not modify the SDK or the docs site.
- Do not run multiple stages in one session.
- Do not add playful motion or decorative flourish.

# FINAL REPORT

Run command; stages complete; route inventory with states; the seam verification result; the honesty
audit; the API specification produced; and your honest assessment of which screens are strong and which
need another pass.

```text
=== END PROMPT W2 ===
```

---

## After it runs — your checklist

- [ ] Open it and try to forget the data is fake. If you can, the indicator is not strong enough.
- [ ] Check the evidence detail view — does replay make determinism *visible*? That is the screen that
      does the most work in a demo.
- [ ] Check the seed data is not uniformly green. A perfect dashboard is a suspicious dashboard.
- [ ] Find an **unenforced** result in the stream. Can you tell at a glance that it is not a breach?
      If it looks like a violation, the prototype is misrepresenting the engine.
- [ ] Find the tenant whose latest contract version was **refused** while an older one still serves.
      Is that legible without narration? It is the state an operator most needs to notice and the one
      logs alone communicate worst.
- [ ] Read the Stage 2 README. That document is the specification for your future NestJS API, and it is
      arguably a more valuable output than the UI itself.
- [ ] Compare against the docs site. Same product, or two products?
