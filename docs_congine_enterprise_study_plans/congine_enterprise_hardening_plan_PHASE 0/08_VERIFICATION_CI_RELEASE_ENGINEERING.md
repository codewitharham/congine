# 08 — Verification, CI & Release Engineering

## Goal

Convert CONGINE's important product claims into continuously verified release properties.

Current evidence is useful: 350 passed / 1 skipped, 92% statement coverage, a 5,000-run determinism test with one verdict, measured native/semantic latency, load shedding, cache behavior, and bounded dead-control-plane behavior. The next step is to turn the strongest claims into regression gates.

---

# Decision Q-01 — Determinism golden corpus

Create a corpus of canonical cases:

```text
contract + input + relevant config
→ expected canonical verdict
```

Run across supported Python versions and production OSes.

Store expected results in stable canonical form.

A difference requires explicit review/migration, not silent acceptance.

---

# Decision Q-02 — Cross-version CI matrix

At minimum, test every Python version CONGINE claims to support.

Do not claim cross-version determinism until the golden corpus passes across the matrix.

When Linux is the production baseline, ensure Linux is mandatory in release CI.

---

# Decision Q-03 — Branch coverage becomes visible

Statement coverage alone can hide untested policy branches.

Enable/report branch coverage and initially observe the real baseline before choosing a hard threshold.

Prioritize branches around:

- fail modes;
- guard modes;
- timeout vs load shed;
- semantic/native paths;
- configuration variants;
- local/remote/offline behavior;
- strict unknown/degraded behavior.

---

# Decision Q-04 — Blocking static typing

Mypy failure should block merge after the configuration is stabilized.

Do not hide failures with `|| true`.

Use targeted ignores with reasons rather than broad suppression.

---

# Decision Q-05 — Architecture boundary tests

Keep/add automated tests that prevent forbidden imports/layer reversals.

Also test substitutability of every port using minimal implementations, not only concrete built-ins.

This is particularly important because the health-port failure escaped the previous architecture model.

---

# Decision Q-06 — Runnable docs/examples are CI assets

Every documentation code example should be an executable source file used by CI.

Do not hand-copy code into documentation if it can drift.

The previously identified LangChain example mismatch should be corrected and protected by tests.

---

# Decision Q-07 — Performance regression suite

Separate fast PR tests from slower release/nightly benchmarks.

Track at least:

- native p50/p95/p99 validation latency;
- semantic validation latency by representative complexity;
- timeout/degradation rate;
- load-shed rejection latency;
- cache get/put scaling;
- initialization against dead control plane.

Do not make noisy microbenchmarks hard PR gates until variance is understood. Use release/nightly budgets where appropriate.

---

# Decision Q-08 — Security/supply-chain automation

Recommended pipeline:

- Ruff format/check;
- Ruff `S` security rules where appropriate;
- bugbear/async rules if compatible;
- mypy;
- `pip-audit`;
- SBOM generation on release;
- dependency review.

Use dedicated Bandit only if Ruff coverage is insufficient; avoid redundant tooling without a clear gap.

---

# Decision Q-09 — Release support matrix

Every release should record:

- supported Python versions;
- production OS support;
- tested storage backends;
- tested integration surfaces;
- migrations/contract-language version;
- known limitations;
- open critical debt;
- evidence link/commands.

---

# Decision Q-10 — No release with unresolved false-safety P0s

A release intended for wider external use should block on defects that can make users believe policy was enforced when it was not.

Examples:

- unknown type fail-open;
- undetected dotted-path ambiguity;
- serialization size-bound fail-open;
- inability to distinguish evaluation failure from policy violation;
- placeholder remote endpoints that may receive credentials.

---

# Decision Q-11 — Evidence commands are reproducible

F05/POC claims should cite exact commands/scripts.

Where feasible, keep measurement scripts in the repository so a future release can rerun them rather than reconstruct methodology from prose.
