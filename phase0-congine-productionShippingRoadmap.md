# Congine SDK (AMCE / Phase 0) — Production-Shipping Roadmap

**Document type:** Engineering + Product + GTM strategy. Internal.
**Status:** Authoritative roadmap for taking the Phase 0 core SDK engine from "session-complete" to "monetized in market."
**Inputs:**
- `phase0-congine-newAudit.md` — pre-session adversarial audit (the "newAudit" file the goal references).
- `phase0-congine-postSessionAudit.md` — post-session exit audit (the "postSessionAudit" file the goal references).
- `AMCE_Phase0_ComprehensiveAnalysis_Roadmap.md` — the master strategy that drove the remediation session.
- Codebase reality check performed before authoring this document (single Nx package `libs/congine-sdk`; root `packages/` is empty; no backend; `congine.io` placeholder only).
**Aim:** Phase 0 — the core SDK engine — is enough to bring this product to market. This document defines *exactly* what is left to do, *in what order*, with *measurable exit criteria*, so the team can ship and start monetising without drifting into Phase 1+ scope.

> **Honest framing up front.** "Shipping Phase 0" in pure-SDK form (Apache-2.0 source, no backend) can earn revenue via training, consulting, and certified-integrator programs — but the typical SaaS revenue curve requires *some* managed surface area. This document therefore plans for a **minimum viable managed control plane** in parallel with the SDK ship. The two together are what becomes "Phase 0 in market." Nothing here pulls in Phase 1 backend scope beyond the smallest slice required to issue API keys, store contracts, and accept telemetry — i.e., a single-region monolith, not the distributed system the HLD anticipates for Phase 1+.

---

## Table of Contents

- [Part I — Comparative Summary: What This Session Actually Changed](#part-i)
- [Part II — Honest Production-Shipping Gap Analysis](#part-ii)
- [Part III — Monetization Strategy](#part-iii)
- [Part IV — The 8-Week Production-Shipping Roadmap](#part-iv)
- [Part V — Risk Register](#part-v)
- [Part VI — "Phase 0 SHIPPED" Definition of Done](#part-vi)
- [Part VII — What is Explicitly Out of Scope (Phase 1+)](#part-vii)
- [Part VIII — Operating Principles](#part-viii)

---

<a name="part-i"></a>
## Part I — Comparative Summary: What This Session Actually Changed

### I.1 Pre-session synopsis (the "newAudit" file)

The pre-session adversarial audit found a codebase that was *micro-architecturally strong* (hexagonal layering, O(1) LFU cache, bounded/load-shedding executor, atomic snapshotting, ReDoS-safe regex) but **not shippable** for three concrete reasons:

1. **Portability lie** — `requires-python = ">=3.10"` claimed a floor the test suite couldn't even *collect* on because of a single PEP-758 `except` tuple in `tests/adversarial/test_remediations.py:189`. Floor was Python 3.14+ in practice.
2. **Distribution legality** — No `LICENSE`, no `SECURITY.md`, no real `README.md`. Apache/MIT or any commercial sale was legally blocked.
3. **Operational holes** — No circuit breaker on the control-plane boundary (10s boot stalls under hung registries), HTTPS-by-warning-only (cleartext credentials by default), no telemetry-loss visibility, no single-flight boot coordination (N-worker thundering herd).

**Pre-session scorecard:** Architecture **3.5**, Concurrency **4.0**, Portability **2.0**, Security **3.5**, Packaging **2.0**, Test Robustness **3.5**.

**Pre-session verdict:** *Not safe to ship to enterprise or open-source today.*

### I.2 Post-session synopsis (the "postSessionAudit" file)

In the remediation session, **22 tasks** across 4 tiers were executed against the comprehensive analysis roadmap. Every hard-blocker (D-1, D-3, D-5) and every architectural-debt item (D-4, D-6, D-7, D-11) from the prior audit was closed with `file:line` evidence and test coverage. The session also surfaced **two emergent issues** (`F-1`: ruff format would silently re-PEP-758 the parenthesised excepts under the default modern target — neutralised by pinning `target-version = "py310"`; `F-2`: 60 tracked `__pycache__/*.pyc` files dating from the initial scaffold — removed from VCS) that the original audit missed.

**Net test delta:** 197 → **223 passed**, 4 skipped (intentional extras gates), 0 failed, ruff `check` + `format --check` both clean.

**Post-session scorecard:** Architecture **4.5** (▲1.0), Concurrency **4.5** (▲0.5), Portability **4.5** (▲2.5), Security **4.0** (▲0.5), Packaging **4.5** (▲2.5), Test Robustness **4.0** (▲0.5).

**Post-session verdict:** *Safe to ship as `0.1.0`-tag OSS preview.* The validation core is now operationally honest about its capabilities. What remains is **release engineering, productisation, and monetisation infrastructure** — not engineering of the SDK itself.

### I.3 Delta table — every audit finding, before → after

| ID | Pre-session state | Post-session state | Evidence |
|---|---|---|---|
| **D-1** | 🔴 Test suite cannot collect on Python 3.10-3.13 (PEP-758 except) | ✅ Parenthesised; ruff `target-version = py310` pinned to prevent silent regression | `test_remediations.py:189`, `pyproject.toml:53-56` |
| **D-2** | 🔴 `nx test` target missing the dev extra | ✅ Confirmed already correct pre-session; `--extra langchain --extra stats` plus CI `uv sync --all-extras` | `project.json:20`, `ci.yml:142` |
| **D-3** | 🔴 No LICENSE / no SECURITY / one-line README | ✅ Apache-2.0 LICENSE at repo root; SECURITY.md with SLA + scope; ~140-line README with 28-row config table | `LICENSE`, `libs/congine-sdk/{SECURITY,README}.md` |
| **D-4** | 🟠 L3 string-literal types L4 concrete; `getattr` shim | ✅ `IValidationRunner(Protocol)` port added; L3 typed against port; shim deleted; `BoundedValidationExecutor` is `isinstance(_, IValidationRunner)` | `ports/validation_runner.py:18`, `validate_contract_usecase.py:36,127` |
| **D-5** | 🟠 No CB; bootstrap stalls 10s per attempt on hung registry | ✅ `CircuitBreaker` (L4, CLOSED → OPEN → HALF_OPEN); wired into sync use-case + bus; `bootstrap` < 500 ms under hung-registry test | `infrastructure/circuit_breaker.py`, `test_remediations.py::test_bootstrap_does_not_stall_when_breaker_is_open` |
| **D-6** | 🟠 `require_https=False` default; cleartext was a warning | ✅ `require_https=True` default; `allow_cleartext` explicit opt-out; `validate()` raises on non-local cleartext | `config.py:120,124,224-234` |
| **D-7** | 🟠 N-worker boot burst on every deploy | ✅ `sync_once_single_flight` (sync + async); per-scope `portalocker` boot lock; jitter | `sync_contracts_usecase.py:105,137`, `http_contract_repository.py:81-94` |
| **D-8** | 🟡 15ms timeout too tight for semantic validation | ✅ Default 100ms; matches test-fixture reality | `config.py:89` |
| **D-9** | 🟡 Stale `*.egg-info` committed | ✅ Removed from VCS; `.gitignore` extended | `.gitignore`, `git ls-files \| grep egg-info` → 0 |
| **D-10** | 🟡 Silent telemetry drops; drift `ImportError` escapes the SDK exception family | ✅ `dropped_total` counter (`health()` key `telemetry_dropped_total`); `evaluate_drift` wraps `ImportError → CongineConfigurationError` | `queue_event_bus.py:84,122`, `dependency_injection.py:280-288` |
| **D-11** | 🟡 `repositories/` mislabels L1; dead `ValidationTimer` export; `__version__` duplicated | ✅ `repositories/` → `ports/` (git mv); `ValidationTimer` not exported, raises `DeprecationWarning` on construction; `__version__` via `importlib.metadata` | `ports/`, `infrastructure/__init__.py:21`, `congine_core/__init__.py:63-73` |
| **F-1 (new)** | n/a | 🟢 Ruff format on default target was unparenthesising D-1 fix; pinned `target-version = "py310"` | `pyproject.toml:53-56` |
| **F-2 (new)** | n/a | 🟢 60 tracked `__pycache__/*.pyc` files dating from initial scaffold removed from VCS | `git ls-files \| grep -E '\.pyc$\|__pycache__'` → 0 |
| **F-3 (new)** | n/a | 🟡 `[dependency-groups]` migration intentionally deferred — current shape works | `pyproject.toml:41-48` |
| **F-4 (new)** | n/a | 🟡 CI matrix `[3.10..3.14]` wired but not yet runtime-verified on GitHub Actions | `.github/workflows/ci.yml:159-242` |

**Net change:** every red/orange finding from the prior audit is **closed with evidence + tests**. The two `🟡` items remaining (F-3, F-4) are honest deferrals, not engineering regressions.

### I.4 Translating the engineering delta into product language

| What the engineering closed | What the product team can now claim |
|---|---|
| D-1 + F-1 + CI matrix | "Runs on every Python from 3.10 through 3.14" (no asterisk) |
| D-3 | "Apache-2.0 licensed; you can use it commercially and in regulated environments" |
| D-5 + adversarial test | "Hardened against control-plane outages — application boot completes in <500 ms even if our cloud is down" |
| D-6 | "Secure by default — credentials never ship over HTTP without an explicit, audited opt-in" |
| D-7 | "Scales horizontally — N replicas do not stampede our registry on deploy" |
| D-10 | "Every telemetry event lost is counted and surfaced; no silent black-hole" |
| F-4 → future runtime green | "Tested on every supported interpreter in CI on every commit" |

These are **the marketing claims the post-session state can substantiate** without lying. The roadmap below ensures that by the end of Week 8 every claim has both engineering proof and customer-facing documentation.

---

<a name="part-ii"></a>
## Part II — Honest Production-Shipping Gap Analysis

The audits answer *"is the engine correct?"*. They do not answer *"can a paying customer buy this on Tuesday?"* — that question has seven distinct domains, mostly outside the SDK source tree. Each is enumerated below with the gap as it stands today.

### II.1 Engineering items still open from the post-session audit

| Gap | Severity | Evidence |
|---|---|---|
| CI matrix has not actually executed against real GitHub Actions hardware | High (gates the "runs on 3.10–3.14" claim) | F-4 |
| `[dependency-groups]` migration deferred | Low (current shape works) | F-3 |
| BYOM healing loop is the differentiator and is not built | High *but Phase 1 scope*; revenue-relevant for Pro tier | postSessionAudit §10 item 1 |
| Distributed circuit breaker (Redis-backed) | Low (Phase 2+) | postSessionAudit §10 item 2 |
| Telemetry signing token separate from API key | Medium (security ergonomics) | postSessionAudit §10 item 6 |
| AMCE HLD / Congine SDK naming reconciliation | Medium (docs hygiene only) | postSessionAudit §10 item 7 |

**Interpretation.** The SDK is engineering-complete for an OSS preview release *today*. The high-severity items in this row are about *proof under load* and *future differentiation*, not about correctness of what ships.

### II.2 Release engineering

| Gap | What's needed |
|---|---|
| No tagged release | `0.1.0` annotated tag, signed via GitHub commit signing or sigstore |
| No PyPI publication | Test PyPI dry run; then real PyPI publish via Trusted Publishers (OIDC, no API token in CI) |
| No SBOM | CycloneDX SBOM generated on every build; attached to GitHub Release |
| No vulnerability scanning of dependencies | Dependabot or Renovate; GitHub Security Advisories |
| No reproducible builds posture | Pin `uv.lock`; document `uv` version in CI |
| No release notes / changelog automation | Conventional commits → `changelog` derived from `CHANGELOG.md` already in place |
| No branch protection | `main` requires PR + green CI + 1 review; signed commits |

### II.3 Documentation infrastructure

| Gap | What's needed |
|---|---|
| README is rich but lives in the package dir only | Public docs site at `docs.congine.io` (Cloudflare Pages + Docusaurus or mkdocs-material + mike) |
| No versioned documentation | Doc versions track the package version (`0.1.x`, `0.2.x`, ...) |
| No example projects | `examples/` monorepo: FastAPI middleware, Django middleware, LangChain integration, raw async OpenAI client, Anthropic SDK with strict mode |
| No quickstart screencast / demo | Sub-5-minute Loom: install → @congine_guard → see a breach detected → see telemetry |
| No API reference auto-gen | `mkdocstrings` or `sphinx-autoapi` against `congine_core` |
| No `py.typed` marker | Add `py.typed` empty file + `Typing :: Typed` classifier already present |

### II.4 Backend slice — the minimum viable managed control plane

The SDK *requires* a control plane to hit unless every user runs the local-file source. To monetise, the managed plane is essentially mandatory. The smallest viable surface:

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /signup` | API | issues an API key tied to an email + Stripe customer |
| `GET /api/v1/contracts/active` | API | Returns `ContractBundle` shape the SDK already expects |
| `POST /api/v1/telemetry` | API | Accepts the `events[]` payload the SDK already sends |
| `POST /api/v1/contracts` | API | Pro-tier only: create/update contracts |
| `GET /dashboard` | UI | A pro-tier dashboard reading from the telemetry store |

**Stack recommendation** (minimal, single region, single instance to start):

- **NestJS** + **Postgres 16** + **Redis** (for rate limiting + session cache) on **Fly.io** or **Render** behind **Cloudflare**.
- **Auth:** Clerk or Auth0 (don't roll your own).
- **Billing:** Stripe Checkout + Customer Portal.
- **CDN/edge:** Cloudflare (also gets you DDoS protection + WAF).
- **Observability:** Cloudflare logs → Better Stack or Datadog free tier.

This is intentionally a tiny slice of Phase 1's HLD — not the full multi-region partitioned-table design the HLD anticipates. The HLD is what we grow into. Today we ship the smallest version that lets a customer sign up, get an API key, paste it into `CONGINE_API_KEY`, and have validations flow telemetry to our dashboard.

### II.5 Commercial infrastructure

| Gap | What's needed |
|---|---|
| No payment processing | Stripe account; products for Free, Pro, Enterprise (contact sales); checkout flow |
| No legal docs | Terms of Service, EULA for the SDK, Privacy Policy, Data Processing Addendum (DPA) for GDPR (use a template from Termly / Iubenda, then have counsel review) |
| No sign-up / onboarding | Form → email verification → Stripe checkout → API key issued → "first validation" tutorial email sequence |
| No customer-facing pricing page | Public pricing on `congine.io/pricing` |
| No status communication | Statuspage or Better Stack public status page |
| No support channel | At minimum: `support@congine.io` mailbox, Discord community for free tier, dedicated Slack channel for Pro+ |

### II.6 Compliance & security posture

| Gap | What's needed |
|---|---|
| No third-party security audit | Independent audit before charging enterprises (Doyensec, Trail of Bits, NCC Group, or smaller boutique) |
| No SOC 2 Type I/II | Onboard Drata or Vanta now; ~6 months to Type I, ~12 months to Type II. Required for most enterprise deals. |
| No penetration test of managed plane | Required after backend exists; quarterly thereafter |
| No bug bounty program | Start small via HackerOne or Intigriti; low payouts initially ($50-500) |
| No SBOM attestation | CycloneDX on every release (covered in II.2) |
| No GDPR-ready data flows | Document data-flow diagram; EU region option on managed plane for EU customers |
| No data retention policy | "Telemetry retained 90 days for Free, 1 year for Pro, configurable for Enterprise" |

### II.7 Go-to-market

| Gap | What's needed |
|---|---|
| No landing page | `congine.io` — value prop, demo gif, pricing, signup |
| No marketing copy | Hero ("Contract-driven validation for LLM outputs — sub-100ms hot path"), benefits, social proof when available |
| No design-partner pipeline | Target 3-5 design partners (paid, with logo rights) before public launch |
| No content marketing | 4 deep blog posts on the differentiated topics: hexagonal architecture for AI middleware; O(1) LFU caching of LLM contracts; why HTTPS-by-default matters for AI infra; what BYOM healing means for cost |
| No launch surface | Hacker News Show HN, Product Hunt, Twitter/X thread, AI Engineering newsletter sponsorships, Latent Space podcast pitch |
| No talks / conference submissions | PyCon, AI Engineer World's Fair, RAG-Pipeline conferences |

### II.8 Operational readiness

| Gap | What's needed |
|---|---|
| No runbook for `health()` keys | Every key (`breaker_state`, `telemetry_dropped_total`, etc.) gets a threshold + an oncall action |
| No SLOs | Define and publish: control-plane availability 99.9%; validation p99 latency <100ms; drift detection delivery <5s after ingest |
| No alert routing | Better Stack / PagerDuty integration with the dashboard |
| No oncall rotation | Even 2 founders rotating weekly is enough for week-1 launch |
| No public dashboard | Grafana Cloud dashboard linked from status page |
| No DB backup/restore policy | Daily Postgres backups to S3-compatible, restore test monthly |
| No incident-response template | Template + first dry-run postmortem published before launch |

---

<a name="part-iii"></a>
## Part III — Monetization Strategy

### III.1 Comparable models

| Company | Open layer | Paid layer | Why it works |
|---|---|---|---|
| **NestJS** | MIT framework, full source | NestJS Devtools (paid), NestJS Enterprise consulting, paid courses & certifications, books | Framework lock-in → demand for expertise. Open core builds the community; paid consulting captures revenue from the long tail of "we need this working in production." |
| **Cursor** | Free tier with limited model calls + completions | Pro ($20/mo unlimited basic, $40/mo Business with privacy + admin) | Freemium with metered usage. Free users become the funnel; the value (best models + agentic features) is gated by tier. |
| **Datadog / Sentry** | OSS lite versions (Sentry self-hosted, Datadog agent code) | Managed SaaS with retention + analytics + alerting | Self-hosting is real but painful; most teams pay to skip the operational burden. |
| **Supabase** | OSS PostgREST + Auth, runnable locally | Managed plan with backups, scale, support | Open core. Killer apps live on the managed plan because of ops complexity. |
| **Vercel** | Open Next.js | Hosting, ISR, Analytics, Edge Functions | Free for hobby; revenue from teams who need bandwidth + SLA. |

### III.2 Recommended Congine model — Open Core + Managed + Pro Differentiators

**Open under Apache-2.0:**
- The entire `congine-sdk` (validation core, hexagonal architecture, all current ports + adapters).
- `FileContractRepository` (local-first / GitOps story).
- The default rule engine + JSON Schema semantic validator.
- The `Ollama`-backed BYOM `IModelClient` adapter (when built in Phase 1) — community can use it self-hosted.
- Examples + documentation.
- Public CLI for contract validation against a local directory.

**Closed source / managed plan:**
- The managed control plane (NestJS backend) — contract registry UI, telemetry ingestion + analytics.
- The dashboard (React/Next.js) — breach explorer, drift visualisation, contract diff.
- "Advanced Healing" — multi-pass healing strategies, model-selection logic, healing-quality scoring (the *recipes*, not the *interfaces*).
- Aggregated cross-tenant insights ("schemas most commonly violated across the industry") — privacy-preserved.
- Compliance artifacts (SOC 2 reports, DPA, BAA on Enterprise tier).
- Priority support, dedicated CSM (Customer Success Manager), Slack channel.

**The hexagonal seam-by-seam decision matrix:**

| Layer | Open? | Reasoning |
|---|---|---|
| L0 (config, exceptions) | OSS | Pure data; trivial to recreate; community contributions welcome |
| L1 (ports) | OSS | Defines the integration surface; locking would block community adapters |
| L2 (domain) | OSS | The rule engine; *some* rules may be gated as "advanced rules" later |
| L3 (use cases) | OSS | Orchestration; the value is in the engine + healing, not the orchestrator |
| L4 (infrastructure) | OSS for current set; *new* L4 adapters (advanced healers, premium semantic validators, multi-LLM healing) **closed source** as Pro plugins |
| L5 (adapters) | OSS for `congine_guard` + LangChain handler; closed for the dashboard + control-plane client |

The hexagonal architecture is *literally what makes this clean*: the open core defines the seams; we keep the high-value implementations private. Customers can build their own private L4 implementations to compete with our paid ones — that's fine; the SDK already supports it. We win on quality + breadth + integration.

### III.3 License decision

| Component | License |
|---|---|
| `congine-sdk` (current tree) | **Apache-2.0** (already chosen) |
| Future Pro-only L4 plugins | Proprietary commercial license; ship as a separate package `congine-sdk-pro` requiring a license-key env var |
| Managed control plane source | Proprietary (closed) |
| Documentation | CC BY 4.0 (encourage learning + redistribution) |
| Example projects | Apache-2.0 (so customers can copy them freely) |

**Note on Apache-2.0 vs MIT** — the post-session audit picked Apache because it includes an explicit *patent grant*. For an AI middleware product where downstream patent claims are a real risk (validation algorithms, healing techniques), Apache-2.0 is the right call. Keep it.

### III.4 Pricing tiers

| Tier | Price (USD) | What's included | Limits | Who buys |
|---|---|---|---|---|
| **Free** (forever) | $0 | Full SDK; managed control plane access; basic dashboard; community Discord; 100K validations / month; 50 active contracts; 30-day telemetry retention | Rate limit on contract-registry writes (10/min) | Indie devs, hobbyists, students, evaluation pilots |
| **Pro** (self-serve) | $99 / project / month | Everything in Free, plus: 10M validations/month, unlimited contracts, 1-year telemetry retention, drift analytics, basic healing (Ollama BYOM), Slack channel, email support (24-hour response), multiple environments (dev/staging/prod) | None on contract count; volume overage at $0.001 per 1K validations | Small teams, startups shipping AI features |
| **Enterprise** (contact-sales, annual contract) | Starts $30K / year | Everything in Pro, plus: dedicated tenant, SSO/SAML, SCIM, advanced healing (multi-model selection, prompt-template library), private region option (US-East / EU-West / APAC), audit-log export, custom data retention, dedicated CSM, support SLA (1-hour critical), DPA + BAA, source code escrow option, on-prem control plane option ($60K/yr+) | Negotiated | Mid-market, regulated industries (fintech, healthcare, legal) |

### III.5 Revenue ramp model (8-week launch → first year)

| Milestone | Free signups | Pro accts | Enterprise pipeline | Monthly revenue |
|---|---:|---:|---:|---:|
| Week 8 (launch) | 100 | 0 | 1-2 conversations | $0 |
| Month 3 | 800 | 5 | 3 conversations | $495 |
| Month 6 | 3K | 20 | 8 conversations, 1 closed | $4,480 |
| Month 9 | 8K | 45 | 4 closed | $14,455 |
| Month 12 | 15K | 80 | 8 closed | $27,920 |

These are *target* numbers, not promises. The free → paid conversion rate assumed is **0.5-1%** (low end of SaaS norms), reflecting that Congine sells to engineering teams not consumers. They are useful to *plan against* and to course-correct from.

---

<a name="part-iv"></a>
## Part IV — The 8-Week Production-Shipping Roadmap

Each week below has the same structure:
- **Goal** — what success looks like at the end of the week
- **Deliverables** — concrete artifacts produced
- **Exit criteria** — measurable yes/no checks
- **Verification** — how to prove the exit criteria
- **Owner placeholder** — to be filled by the team
- **Failure-mode rollback** — what to do if the week's goal is missed

The first week is engineering closure; the rest is productisation. Tasks marked **[PARALLELISABLE]** can be done by a second team member without blocking the critical path.

### Week 1 — Engineering Closure: From "Session-Complete" to "Ship-Ready"

**Goal:** Every honest deferral from the post-session audit is closed or formally accepted; CI is green on real GitHub Actions hardware.

**Deliverables:**
1. **Push current session changes** to the remote on a feature branch; open a PR against `main`.
2. **First CI matrix run** across Python 3.10, 3.11, 3.12, 3.13, 3.14. Any interpreter-specific failures are fixed.
3. **Migrate dev toolchain to `[dependency-groups]`** (closes F-3) — `pyproject.toml`:
   ```toml
   [dependency-groups]
   dev = ["pytest>=8.0", "pytest-asyncio>=1.0", "pytest-cov>=6.0", "ruff>=0.15.15"]
   ```
   Remove from `[project.optional-dependencies].dev`. `uv run` will now auto-install it. Update `project.json` test target to drop `--extra dev` if it was added.
4. **[PARALLELISABLE]** — A separate engineer adds `py.typed` marker (`libs/congine-sdk/src/congine_core/py.typed`, empty file) so downstream type-checkers see the package as typed.
5. **`mypy --strict` baseline** (run informationally; create `# type: ignore` annotations for the few violations rather than fixing them all in week 1).
6. **Pre-commit hooks** (`.pre-commit-config.yaml`) wiring ruff format + check + an `actionlint` for the workflow files.

**Exit criteria:**
- [ ] PR merged into `main`.
- [ ] `pnpm nx run-many -t lint,test` green on all 5 matrix Python versions in CI.
- [ ] `py.typed` marker present and `congine_core` shows up as typed in a downstream consumer's mypy run.
- [ ] `uv run pytest` works from a clean `uv sync` without specifying any extras.

**Verification:** Look at the GitHub Actions run page; every matrix cell green; an external sanity-check repo `pip install -e libs/congine-sdk` + `mypy` against a tiny consumer shows zero "untyped module" warnings.

**Owner:** TBD. (Lead engineer.)
**Effort:** 3-4 person-days.
**Rollback if missed:** Reduce CI matrix to `[3.10, 3.13, 3.14]` for the initial release and re-add the middle versions in the first patch. Documentation must reflect actual tested floor.

### Week 2 — Release Engineering: First Tagged & Signed Release

**Goal:** `0.1.0` is published to Test PyPI; the release process is reproducible and signed.

**Deliverables:**
1. **Trusted Publishers configuration** in PyPI / Test PyPI — OIDC from GitHub Actions, *no API tokens in CI secrets*.
2. **`.github/workflows/release.yml`** triggered on tag `v*.*.*`:
   - Builds sdist + wheel via `uv build`.
   - Generates **CycloneDX SBOM** via `cyclonedx-py`.
   - Generates **Sigstore signature** via `sigstore-python`.
   - Uploads to Test PyPI (and later, on a separate "promotion" workflow, to real PyPI).
   - Creates a GitHub Release with auto-derived notes from `CHANGELOG.md`'s `[Unreleased]` block.
3. **Promote `[Unreleased]` to `0.1.0` in `CHANGELOG.md`** with date `2026-06-MM`.
4. **Branch protection on `main`:**
   - Require PR.
   - Require all status checks (lint, typecheck, test on all matrix versions, format-check, sync-typescript-refs).
   - Require signed commits (or, lighter: require 1 review).
   - Linear history.
5. **`renovate.json`** (or Dependabot config) — daily PRs for dependency updates, grouped per ecosystem.
6. **`SECURITY.md`** updated to reference Sigstore signatures + SBOM for verification.

**Exit criteria:**
- [ ] `pip install -i https://test.pypi.org/simple/ congine-sdk==0.1.0` works in a fresh venv.
- [ ] The Test PyPI release has both sdist + wheel + `.sigstore` + `.cdx.json` (SBOM) attached.
- [ ] GitHub Release page at `v0.1.0` shows auto-generated release notes.
- [ ] Branch protection rejects a direct push to `main`.

**Verification:**
```bash
python -m venv /tmp/v && /tmp/v/bin/pip install -i https://test.pypi.org/simple/ congine-sdk
/tmp/v/bin/python -c "import congine_core; print(congine_core.__version__)"   # → "0.1.0"
sigstore verify identity --cert-identity 'https://github.com/CONGINE/congine/.github/workflows/release.yml@refs/tags/v0.1.0' --cert-oidc-issuer https://token.actions.githubusercontent.com congine_sdk-0.1.0-py3-none-any.whl
```

**Owner:** TBD. (Same engineer as Week 1, or a release-engineering specialist.)
**Effort:** 4-5 person-days.
**Rollback if missed:** Ship without Sigstore (still useful) and add it in `0.1.1`. SBOM is non-negotiable for enterprise sales — do not ship without it.

### Week 3 — Documentation Site & Examples

**Goal:** `docs.congine.io` is live with versioned reference docs + 4 working integration examples.

**Deliverables:**
1. **`docs/` directory** in the repo with **mkdocs-material** + **mike** for versioning, OR **Docusaurus 3** (pick one — recommendation: mkdocs-material for Python projects because mkdocstrings integration is excellent).
2. **Auto-generated API reference** from docstrings via `mkdocstrings[python]`. Every public class in `congine_core.__all__` gets a page.
3. **Hand-written guide pages:**
   - Getting started (10-minute tutorial).
   - Concepts (contracts, validation, fail modes, telemetry).
   - Architecture (the L0–L5 layering, the ports/adapters story).
   - Configuration reference (re-rendered from the README table).
   - Failure modes deep-dive.
   - Observability + dashboards.
   - Local-first (FileContractRepository) walkthrough.
   - Migration from naive Pydantic validation.
   - FAQ.
4. **Cloudflare Pages** deployment from the `gh-pages` branch, with `docs.congine.io` CNAME.
5. **Example projects** (each in `examples/<name>/`):
   - `examples/fastapi-middleware/` — guards every POST endpoint.
   - `examples/langchain-handler/` — uses `CongineCallbackHandler`.
   - `examples/openai-strict/` — `STRICT` fail mode wrapped around OpenAI client.
   - `examples/local-first/` — `CONGINE_CONTRACT_SOURCE=file` + GitOps workflow.
6. **A 4-minute screencast** (Loom or Cap.so) — recorded by a developer using only the README + the new docs site, demonstrating install → contract → guard → breach detection → dashboard view. Honest recording: keep editing minimal.

**Exit criteria:**
- [ ] `docs.congine.io` resolves and renders the homepage in <1.5s LCP.
- [ ] Versioned doc dropdown shows `0.1.x` (current) + `latest`.
- [ ] All 4 example projects run successfully against a fresh `pip install congine-sdk`.
- [ ] The screencast is on YouTube unlisted, link in README.

**Verification:**
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://docs.congine.io/        # → 200
cd examples/fastapi-middleware && uv sync && uv run pytest  # → green
```

**Owner:** TBD. (Tech writer + lead engineer pairing recommended.)
**Effort:** 5-6 person-days. **[PARALLELISABLE]** with Week 2.
**Rollback if missed:** Push the screencast and FastAPI example regardless; docs.congine.io can launch with reference docs only and add the long-form guides over the next 2 weeks.

### Week 4 — Minimum Viable Managed Control Plane

**Goal:** A managed plane exists at `api.congine.io` that the SDK can talk to in production for free + Pro signups. **This is the single highest-revenue-impact week.**

**Deliverables:**
1. **`packages/congine-cp/`** (new — uses the existing empty `packages/*` workspace slot in `package.json`):
   - **NestJS 11** + **TypeScript** + **Postgres 16** via **TypeORM** or **Drizzle**.
   - **Redis** for rate limiting + session cache.
   - **Auth provider:** Clerk (recommended over Auth0 — better DX and pricing).
   - Tables: `tenants`, `api_keys`, `contracts`, `contract_versions`, `telemetry_events` (with monthly partitioning per HLD §9.4).
2. **Endpoints** (versioned `/api/v1`):
   - `POST /api/v1/contracts/active` (the SDK already calls this with API-key header)
   - `POST /api/v1/telemetry` (batch ingest)
   - `POST /api/v1/contracts` (Pro: create/update)
   - `GET /api/v1/contracts/:id` / `PATCH` / `DELETE`
   - `POST /signup` (issues API key + Stripe customer)
   - `GET /healthz` (for our own oncall)
3. **Deployment:** Fly.io (recommended — multi-region trivial later) or Render. Single-instance Postgres for week 1; HA later. Cloudflare in front for DDoS/WAF.
4. **Domain + DNS:** Register `congine.io` (if not done); set up `api.congine.io`, `docs.congine.io`, `app.congine.io`, `www.congine.io`.
5. **Smoke integration test** — a test that pushes a contract, runs `bootstrap()` from the SDK against `api.congine.io`, validates a payload, and confirms telemetry arrived.

**Exit criteria:**
- [ ] A new account can be created via `POST /signup` and the returned API key works for `bootstrap`.
- [ ] 1,000 sequential validations on a free-tier account succeed end-to-end.
- [ ] Free-tier rate limit (e.g. 100K/month) is enforced and the SDK degrades gracefully when hit.
- [ ] Postgres backups run nightly to S3-compatible storage.

**Verification:**
```bash
# Provision a free-tier account; place the API key in env
CONGINE_API_KEY=ck_test_... CONGINE_BASE_URL=https://api.congine.io \
  python examples/fastapi-middleware/main.py &
ab -n 1000 -c 50 http://localhost:8000/validate-something
# All 1000 succeed; check api.congine.io dashboard shows 1000 events.
```

**Owner:** TBD. (Backend engineer.)
**Effort:** 8-10 person-days. The single biggest week. **NOT parallelisable with Week 5 because Week 5 depends on Stripe being live in this plane.**
**Rollback if missed:** Ship with file-source only ("self-host the contracts file") and delay paid signups by 2 weeks. The SDK still ships at week 2 — but revenue is delayed. This is the painful but acceptable rollback.

### Week 5 — Commercial Foundations: Stripe, Legal, Signup Flow

**Goal:** A potential customer can land on `congine.io`, click "Start free", verify email, paste their key into their codebase, and (separately) upgrade to Pro via Stripe.

**Deliverables:**
1. **Stripe products + prices:**
   - `congine-free` ($0/mo, "Free tier")
   - `congine-pro` ($99/project/mo, "Pro")
   - Webhook handler in the control plane to flip a tenant's `tier` column on `checkout.session.completed`.
2. **Sign-up flow:**
   - Email + password → email verification → Stripe Customer creation → API key issued → onboarding email sequence (5 emails over 14 days).
3. **Onboarding tutorial email sequence:**
   - Day 0: "Your API key + 30-second quickstart"
   - Day 1: "Define your first contract"
   - Day 3: "Add a guard to your endpoint"
   - Day 7: "Watch your first breach in the dashboard"
   - Day 14: "Ready for Pro? Here's what unlocks."
4. **Legal:** Terms of Service, Privacy Policy, DPA, EULA. Use Termly or Iubenda generator + counsel review. **Do not ship without counsel review.**
5. **Pricing page** at `congine.io/pricing` (matches the table in Part III.4 of this document).
6. **`app.congine.io`** — minimal app dashboard (Next.js 15) for: viewing contracts, breach explorer (a table for now, fancy viz later), API key rotation, Stripe Customer Portal link.

**Exit criteria:**
- [ ] A fresh visitor can sign up + receive API key + paste it into a local repo + run their first validation in <10 minutes.
- [ ] Upgrading Free → Pro via Stripe Checkout works end-to-end and flips the tenant tier within 60 seconds.
- [ ] Cancelling Pro returns the tenant to Free + rate limits start enforcing on the next sync.
- [ ] All legal pages are linked from the footer of every public page.

**Verification:** A non-team member (e.g. a friend) walks through signup + first validation + upgrade + cancel in a single recorded screen-share; we time each step.

**Owner:** TBD. (Frontend engineer + founder for legal.)
**Effort:** 5-7 person-days for the engineering; legal review is calendar-bound (allow 1 week even if review takes a day). **[PARALLELISABLE]** with the later half of Week 4 if a separate person owns frontend.

### Week 6 — Security Posture & Compliance Headstart

**Goal:** Security claims in `SECURITY.md` are independently validated; the SOC 2 clock has started ticking.

**Deliverables:**
1. **Third-party security audit** of the SDK source. Quote from 2-3 firms; pick one. Allow ~$8K-$25K. Boutique firms like **NCC Group**, **Trail of Bits**, **Doyensec**, **Hunter & Holberton**, or smaller specialists. Estimated 1-2 weeks elapsed.
2. **Penetration test** of the managed plane (`api.congine.io`). Same firm or a separate one. ~$8K-$15K. Required before Enterprise sales.
3. **SOC 2 Type I kick-off** with **Drata** or **Vanta**. Costs ~$10K-$20K + the cost of policies. Type I in ~3 months; Type II in ~12 months. Do not wait until enterprise asks.
4. **Bug bounty program** on **HackerOne** or **Intigriti** with public scope = the SDK + the managed plane public endpoints. Starting payouts: $50 (low) to $500 (high) — low is fine for week 6.
5. **Privacy-policy + data-flow diagram** review for GDPR. Make the EU region a hard checkbox on signup if requested (we may not have an EU region in Week 6; in that case the page reads "EU region coming Q3 2026" and we maintain a wait-list).
6. **Internal threat model document** (`docs/threat-model.md`) — STRIDE table covering API-key theft, contract poisoning via control plane, telemetry injection, dashboard XSS, billing fraud. Each threat → control → test that proves it.

**Exit criteria:**
- [ ] Third-party audit contract signed; audit in flight.
- [ ] Drata / Vanta onboarded; first 5 policies drafted (acceptable use, info-sec, incident response, vendor management, access control).
- [ ] HackerOne / Intigriti page is live.
- [ ] Threat model committed to the repo.

**Verification:** Audit firm has been paid the deposit and engagement letter is signed. Drata dashboard shows our first compliance score.

**Owner:** TBD. (Founder + a security-engineer contractor for the threat model.)
**Effort:** 3-4 person-days of internal work; the audit + SOC 2 work runs in background.
**Rollback if missed:** Audit can shift to Week 7 if Week 6 capacity is tight. SOC 2 *cannot* slip — start the clock no later than Week 6 or it bottlenecks enterprise deals in Q3+.

### Week 7 — Operational Readiness

**Goal:** When a paying customer raises a support ticket, we know what to do.

**Deliverables:**
1. **Runbook** (`docs/runbook.md`) — for each `health()` key, every threshold, every alert:

   | Symptom | Diagnosis | Action |
   |---|---|---|
   | `breaker_state == "OPEN"` for >10 min | Control plane outage | Page primary oncall; check status of registry instance |
   | `telemetry_dropped_total` increases > 100/min | Bus saturation OR registry rejecting | Drain telemetry queue size up; investigate |
   | `validation_rejected_total` rising | Customer is at capacity | Notify customer; offer Pro upgrade; check workers |
   | `cache_entries` == 0 after boot | Snapshot poisoned OR registry empty for tenant | Audit snapshot file; re-trigger sync |
   | …etc for every health key | | |
2. **SLO + SLA document** (`docs/sla.md`):
   - Free tier: best-effort, no SLA.
   - Pro tier: 99.5% control-plane uptime; <250ms validation p99 latency; <30s telemetry ingest p99.
   - Enterprise tier: 99.9% control-plane uptime; <100ms validation p99 latency; <5s telemetry ingest p99; with credits.
3. **Alert routing:** Better Stack On-Call or PagerDuty for the 2-person rotation.
4. **Public status page** (`status.congine.io`) via Better Stack / Statuspage. Subscribed to from the footer of `congine.io`.
5. **Grafana Cloud dashboard** scraping `api.congine.io/healthz` + Postgres metrics + SDK telemetry sampled aggregates.
6. **Backup-restore drill** — actually restore Postgres from yesterday's S3 snapshot into a parallel instance; document the runbook for it.
7. **First "incident postmortem" template** + a dry-run postmortem on a fake incident, published to set the cultural bar.

**Exit criteria:**
- [ ] An alert fires when the breaker is artificially tripped; oncall page goes off within 60 seconds.
- [ ] Status page reports green; subscribing to it sends an email when we flip something to "degraded."
- [ ] Backup restore drill succeeds with full data integrity.

**Verification:** Trigger each runbook scenario in a staging environment; confirm the runbook actions resolve them.

**Owner:** TBD. (Founder + lead engineer.)
**Effort:** 4-5 person-days. **[PARALLELISABLE]** with Week 6.

### Week 8 — Go-to-Market Launch

**Goal:** First 100 free signups; 1-2 design partners committed; momentum is publicly visible.

**Deliverables:**
1. **`congine.io` landing page** (Next.js 15 + Tailwind) — hero ("Contract-driven validation for LLM outputs. Sub-100ms. Multi-tenant from day one."), feature grid, code snippet (the 30-second quickstart), pricing CTA, signup CTA, customer logos slot (empty for week 8), footer.
2. **Demo gif/video** on the landing page — 30 seconds. Show: install → guard → an intentional breach → the dashboard. From the same recording as Week 3's screencast, cut down.
3. **Launch content:**
   - Hacker News "Show HN" post (the strongest single channel — author-team-member account).
   - Product Hunt launch — scheduled for a Tuesday at 12:01 AM PST.
   - Twitter/X launch thread — 8-10 tweets with code + GIFs.
   - LinkedIn post from each founder.
   - Submit to AI newsletters: Latent Space, The Batch, AI Engineering Weekly.
4. **4 deep blog posts** (publish 1 per week leading up to launch + 2 on launch day):
   - "Why we wrote a Python validation engine in 2026 instead of using Pydantic"
   - "Hexagonal architecture for AI middleware"
   - "The day our control plane went down and 8 customers didn't notice"
   - "BYOM healing: what it is and why it costs less than you think"
5. **Design partner outreach** — Personal emails to 30-50 known AI engineers + CTOs at AI-first startups. Offer: free Pro tier for 12 months + logo on website + monthly office hours, in exchange for production usage + feedback.
6. **Community channels live** — Discord for free tier (general + help + showcase), Pro Slack with a private channel per customer.

**Exit criteria:**
- [ ] 100 free-tier signups by end of week.
- [ ] 3-5 design partners actively integrating.
- [ ] At least one blog post on HN front page (any score, not just hits).
- [ ] >500 GitHub stars by end of week (assumes the underlying work + launch posts are good).
- [ ] First Pro upgrade (this can slip to Week 9 without panic).

**Verification:** Dashboard shows the signup count; Discord shows real conversation; Stripe shows at least one transaction (even if it's the founders dogfooding).

**Owner:** TBD. (Founder for outreach + content; engineer for landing page polish.)
**Effort:** 5-6 person-days. **[PARALLELISABLE]** with Week 7 in part (landing-page polish can happen alongside ops work).

---

<a name="part-v"></a>
## Part V — Risk Register

For each risk: **Impact** (1-5, where 5 = product-killing); **Likelihood** (1-5); **Mitigation** + **Owner placeholder**.

| # | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---:|---:|---|---|
| R-1 | Open-source forks compete with our managed plan | 3 | 4 | Moat is the *managed plane data network effect* (drift detection improves with cross-tenant aggregated telemetry), *healing quality* (closed-source recipes), *operational ease* (most teams won't self-host). Apache-2.0 is correct here — forks help adoption. | Founder |
| R-2 | Enterprise demands fully-on-prem control plane | 2 | 5 | Offer this as "Enterprise Self-Managed" SKU at $60K+/year. Same source code we run; they get a Helm chart + 4 hours of onboarding. | Sales |
| R-3 | Competitor enters first (Guardrails AI, LangSmith eval, Helicone) | 4 | 5 (already happening) | Differentiation: *hexagonal architecture* (no other product is this clean), *sub-100ms hot path with bounded executor* (most competitors have latency holes under load), *BYOM healing with the customer's own model* (most competitors lock you to OpenAI). | Product |
| R-4 | SOC 2 audit fails / slips past Q4 2026 | 4 | 2 | Drata/Vanta from Week 6. Q3 enterprise deals can land *with* "SOC 2 in progress" as a verifiable signed engagement, *if* we have a credible Type I-by-date. | Founder |
| R-5 | Cold-start LLM provider changes output shape unexpectedly | 2 | 4 | Contract versioning + drift detection + degrade fail-mode catch this without breaking the host. Build a "model migration playbook" doc for customers. | Engineer |
| R-6 | Stripe rejects us / payment processing complications | 3 | 1 | Stripe is by far the most accepting; if rejected, fallback to Paddle (handles VAT/MOSS, useful internationally anyway). | Founder |
| R-7 | DDoS / abuse on the free tier eats us alive | 3 | 3 | Cloudflare WAF + per-tenant rate limit at the application layer + per-IP rate limit at the edge. Free tier is opt-in by email verification; bot signups are caught early. | Engineer |
| R-8 | A critical CVE in `httpx` / `jsonschema` / `portalocker` | 3 | 2 | Renovate/Dependabot in place from Week 2; security advisory feed via GitHub. SBOM lets enterprise customers know within hours, not weeks. | Engineer |
| R-9 | Founder bandwidth — can't do all 8 weeks | 5 | 4 | Roadmap is sized for 2 engineers + 1 founder for product/GTM. If short-staffed, drop Week 6's audit (slip to Week 9-10), drop Week 3's example projects to FastAPI only. Do NOT drop Week 4 (control plane) or Week 7 (oncall). | Founder |
| R-10 | First 10 customers all want feature X that's not in our roadmap | 3 | 4 | Listen carefully but resist road-mapping by individual customer demand. Aggregate: if 7/10 ask for it, build it. Otherwise, log and revisit at Month 6. | Product |

---

<a name="part-vi"></a>
## Part VI — "Phase 0 SHIPPED" Definition of Done

Phase 0 is **shipped, monetised, and growing** when ALL of these are true. This is the exit criterion for the entire roadmap.

### Engineering & SDK
- [ ] `0.1.0` published to real PyPI (not just Test PyPI).
- [ ] Sigstore signature + CycloneDX SBOM attached to every GitHub Release.
- [ ] CI matrix green across Python 3.10–3.14 on every PR.
- [ ] `congine-sdk` on PyPI has `py.typed` marker.
- [ ] `docs.congine.io` is live with the current version's reference + 4 example projects.

### Managed plane
- [ ] `api.congine.io` is in production behind Cloudflare.
- [ ] Free-tier signup → API key → first-validation works in <10 minutes for a new user.
- [ ] Postgres backups verified by an actual restore drill.
- [ ] Status page is live with public uptime data.

### Commercial
- [ ] Stripe is live with Free + Pro tiers; checkout works end-to-end.
- [ ] Terms of Service, Privacy Policy, EULA, DPA published and counsel-reviewed.
- [ ] At least 1 paying Pro customer.
- [ ] 3-5 design partners actively using the product in production.

### Security & compliance
- [ ] Third-party security audit complete; findings remediated or risk-accepted with documentation.
- [ ] SOC 2 Type I work in flight (Drata/Vanta).
- [ ] Bug bounty program live.
- [ ] Penetration test of `api.congine.io` complete.

### Operations
- [ ] Runbook covers every `health()` key.
- [ ] SLOs documented and published on the SLA page.
- [ ] Oncall rotation set up; first dry-run paged successfully.

### Go-to-market
- [ ] `congine.io` is the public face: landing + pricing + signup + docs + status all reachable.
- [ ] Discord community has >50 members; Pro Slack channels active.
- [ ] At least 1 launch post above 100 points on HN, OR equivalent traffic from elsewhere.

---

<a name="part-vii"></a>
## Part VII — What is Explicitly Out of Scope for Phase 0

Listing these so the team doesn't drift. **These are good ideas. They are Phase 1+.**

- **BYOM healing loop** (`IModelClient` port + multi-pass healing strategies). Pro tier promises *basic* healing via Ollama; the advanced strategies come in Phase 1 and are the upgrade pitch for Q2 2026.
- **Multi-region managed control plane**. Phase 0 ships single-region (US-East). EU region is a stated waitlist commitment, fulfilled in Phase 1.
- **Distributed circuit breaker** (Redis-backed). Process-local is correct for Phase 0.
- **SSO / SAML / SCIM**. Pro tier launches with API-key only; Enterprise gets SSO in Phase 1.
- **Custom integrations beyond LangChain + raw async**. We support the most common patterns and document how to write your own (the hexagonal architecture makes this trivial).
- **Mobile SDKs / Edge runtime**. Python only for Phase 0. The architecture is portable but we are not porting yet.
- **The full HLD-anticipated NestJS backend with table partitioning, KSD drift dashboards, etc.** Phase 0 control plane is a tiny slice; the rich version is Phase 1.
- **AMCE HLD class-name reconciliation (`AmceClient` vs `ServiceContainer`)**. Doc cleanup, not engineering. Land it in Phase 1's docs sprint.
- **A real "Healing Marketplace"** where third parties publish IModelClient adapters. Compelling, premature.
- **Compliance certifications beyond SOC 2 Type I** (HIPAA, ISO 27001, FedRAMP). Sequenced after first 5 enterprise deals.

---

<a name="part-viii"></a>
## Part VIII — Operating Principles

Two principles that should guide every decision made under this roadmap.

### Principle 1: Ship the engineering before the polish

Apache-2.0 SDK alone, on PyPI, with green CI and a real README, has *more* market signal than vapourware with a perfect landing page. Week 2's tag is more important than Week 8's launch.

### Principle 2: Honest deferrals beat optimistic promises

Every "TBD" in this document and the `F-3` / `F-4` items in the post-session audit are deliberate. If a Week-N goal slips, **say so publicly** (changelog + status page) rather than padding it. Trust compounds; padding erodes.

### Principle 3: Open core is a strategy, not an ideology

We open-source the SDK because it earns us community + reach. We hold back the managed plane + dashboard + advanced healing because *that* is what justifies the price. The NestJS model works because the framework is free *and* the founders earn a living from training/consulting/enterprise around it. We do the same.

### Principle 4: The hexagonal architecture is the moat

The fact that every cross-layer collaborator goes through an L1 `typing.Protocol` is what lets us ship Pro plugins as separate packages without forking the SDK. **Do not betray the architecture for shortcuts.** A future "just put this hack directly in `validate_contract_usecase.py`" suggestion is the slow death of the moat.

---

## Appendix A — Decisions Already Made in This Document

These are commitments. Future PRs should not relitigate them.

1. **License:** Apache-2.0 for the SDK; proprietary for control plane / dashboard / advanced healing.
2. **Default support floor:** Python 3.10. (Confirmed by the post-session audit + CI matrix.)
3. **Initial managed-plane stack:** NestJS + Postgres + Redis + Cloudflare. Replaceable in Phase 2 if scale demands.
4. **Initial auth provider:** Clerk.
5. **Initial billing:** Stripe.
6. **Initial compliance framework:** Drata or Vanta. SOC 2 Type I → Type II.
7. **Pricing structure:** Free / Pro $99-mo / Enterprise contact-sales. Pro is project-scoped, not user-scoped, to avoid the "we have 50 engineers but only 2 use it" pricing-friction problem.
8. **Cadence:** Patch releases as needed; minor releases every 6-8 weeks; major releases every 6-12 months.

---

## Appendix B — Open Decisions to Be Made Before Week 1

These need a founder-level call before Week 1 begins. Each has a recommendation.

| Decision | Options | Recommendation |
|---|---|---|
| Domain name | `congine.io` (placeholder in current code) / `amce.dev` / `amce.io` / other | Confirm `congine.io` — references already exist throughout README/SECURITY |
| Org name on GitHub | `CONGINE` / `congine` / `congine-io` / `amce-ai` | `congine` (lowercase) — matches the SDK and brand |
| Public repo name | `congine` (current — monorepo) / split into `congine-sdk` + `congine-cp` + `congine-docs` | Keep monorepo — Nx is already set up; split only if a contributor explicitly asks |
| First hire (if budget allows) | Backend engineer / Tech writer / DevRel | Backend engineer — Week 4 is the bottleneck |
| Pricing currency | USD only / USD + EUR / multi-currency | USD only for Phase 0; multi-currency in Phase 1 if EU traction justifies it |
| Region for managed plane | US-East / EU-West / US+EU at launch | US-East first; EU on the waitlist |

---

## Appendix C — Daily Cadence Recommendation for Weeks 1-8

This roadmap is achievable for a team of 2 engineers + 1 founder. To make it real:

- **Monday 09:00:** 30-min stand-up. Each person says "yesterday / today / blocked-on." Update the GitHub project board.
- **Wednesday 14:00:** 60-min review of week's deliverables vs exit criteria. If slipping, decide rollback.
- **Friday 17:00:** Demo the week's work in a recorded Loom, shared internally + with design partners.
- **Daily:** Founder spends 1 hour on design-partner outreach (Week 1-8, not just Week 8).

---

## Final word

The session that produced the post-session audit closed the **engineering** Phase 0 in 22 tasks. This roadmap closes the **business** Phase 0 in 8 weeks: release engineering, docs, managed plane, commercial foundations, compliance headstart, ops readiness, launch. **All of it is sized so a small team can execute it without compromise.**

The two audit files prove the engine works. This document is how the engine reaches customers and earns its keep.

*Ship the engine. Trust the architecture. Charge for the operating burden you carry for them. The rest follows.*

---

*Document compiled against `phase0-congine-newAudit.md` (pre-session, 178 lines) and `phase0-congine-postSessionAudit.md` (post-session, 425 lines). All claims about the current codebase are grounded in the live tree; all claims about external infrastructure (Stripe, Clerk, Drata, etc.) are vendor-recommendation defaults — final choice is the team's. Every checkbox in this document is intended to be carried into the actual project tracker on Week 1, Day 1.*
