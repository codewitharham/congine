# Claude Code Prompt — Congine Deep System Analysis & Reverse Engineering
### (Document 2 — the authoritative, exhaustive, re-runnable system map generator)

```
=== PROMPT START ===

ROLE
You are a Principal Backend Systems Architect performing a complete, ground-truth reverse
engineering of the Congine codebase. You are not writing a report to impress anyone. You are
building a TRUE, COMPLETE, FILE-ACCURATE understanding of what has actually been built, explained
the way a senior engineer explains a system to another engineer who must maintain it: in plain
human language, with full narrative linkage between files, not as a list of class names and
diagrams. The reader is the founder. The founder understands concepts well but does NOT
automatically understand structure from names — every relationship must be spelled out in prose.

ABSOLUTE RULES (read before doing anything)
1. READ EVERYTHING. Do not sample. Do not assume. Do not infer a file's behavior from its name —
   open it and read it. If you have not read a file, you may not describe it.
2. GROUND TRUTH ONLY. Every claim about the code must be traceable to a file and a construct you
   actually read. Where you are uncertain, say "UNCERTAIN — needs runtime confirmation" rather than
   guessing. Never present an inference as a fact.
3. HUMAN FORM. Explain in full sentences and paragraphs. For every component, the reader must
   understand: what problem it solves, what it receives, what it produces, who calls it, what it
   calls, what happens when it succeeds, and what happens when it fails. A diagram is never
   sufficient on its own — it must be accompanied by a narrative walkthrough.
4. LINKAGE IS THE POINT. The single most valuable output is the FILE-TO-FILE LINKAGE MAP: how a
   request flows from entry to exit, naming every file it passes through and what each does to it.
   Trace the real call paths, not idealized ones.
5. DO NOT MODIFY CODE. This is a read-and-document task only. Make zero edits to source files.
   The only files you create are the documentation outputs specified below.
6. TOKEN DISCIPLINE. Read thoroughly but write efficiently. Prefer precise prose over padding.
   Do not repeat the same explanation in multiple files — cross-reference instead.

STEP 0 — LOCATE THE CODEBASE (do this first, adapt if needed)
The Congine SDK is expected at:  libs/congine-sdk/
The core package is expected at: libs/congine-sdk/src/congine_core/
If that path does not exist, discover the real layout by running, from the repository root:
   find . -type f -name "*.py" -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*"
and also inspect any of: pyproject.toml, setup.py, setup.cfg, README*, and any docs/ directory.
Establish the actual root of the Python package before proceeding. State clearly in your output
what the real paths are. From here on, "the codebase" means every Python source file you found,
plus configuration (pyproject.toml, etc.), plus existing docs and tests.

STEP 1 — INVENTORY (build the map of territory before exploring it)
Produce a complete file inventory. For EVERY source file, record: its path, its apparent layer
(see Step 2), a one-line statement of its responsibility (after reading it, not after reading its
name), its primary public constructs (classes/functions actually defined), and its imports of
OTHER project files (this is the raw material for the linkage map). Do not skip test files —
note them separately but completely. Output this as the file inventory section.

STEP 2 — IDENTIFY THE SEAMS (name the architecture as it actually is)
This project is intended to follow a layered hexagonal architecture, conceptually:
   - Shared/cross-cutting (config, models, exceptions, constants)
   - Protocols/abstractions (the interfaces — typing.Protocol seams)
   - Pure domain (business rules with no infrastructure dependencies)
   - Use cases (orchestration of domain + protocols)
   - Infrastructure (concrete implementations: cache, http, queue, timers, etc.)
   - Adapters / entry points (the decorator, framework integrations, DI container)
For EACH layer, list which actual files belong to it, and CONFIRM OR CHALLENGE whether the code
respects the layer boundaries. Specifically check: does the pure-domain layer import any
infrastructure? Do any abstractions live in the wrong layer? Where the actual structure diverges
from the intended one, say so plainly and explain the consequence. Do not assume the intended
architecture is the real one — verify it against what you read.

STEP 3 — TRACE THE PRIMARY PATH END TO END (the most important section)
Identify the single most important thing the system does — the validation of a decorated function's
output — and trace ONE request through the entire system, in narrative prose, naming every file and
construct it touches in order. The walkthrough must answer, at each handoff:
   - What just arrived, and from where?
   - Which file/function now has control, and what does it do to the data?
   - What does it call next, and why?
   - What does it return, and to whom?
Cover the full journey: the developer's function returns a value → the decorator intercepts → the
container/dependency wiring resolves the needed pieces → validation executes (each of the structural
rules, in the real order) → the verdict is produced → the enforcement decision is made (allow /
block / whatever modes exist) → telemetry is emitted (trace this async path too) → the value is
(or isn't) returned to the caller. Then produce a sequence diagram, but ONLY as a companion to the
prose — the prose is primary.

STEP 4 — TRACE THE BRANCHES AND FAILURE PATHS (where the real system lives)
Now trace what happens when things go wrong, because this is where the truth of a system is. For
each of the following, narrate the actual code path and state whether it is handled correctly,
partially, or not at all:
   - The decorator is used with NO explicitly provided container/dependencies (the default path).
     What actually gets constructed, and when? Is anything bootstrapped? Trace it precisely.
   - The schema/contract cache is cold or misses. What happens?
   - The network/backend is unavailable. What is the fallback? Is there an offline snapshot? Where
     is it stored, how is it scoped, and is that scoping safe across multiple tenants on one host?
   - Validation exceeds its time budget. What cancels it? Can the work actually be cancelled? What
     happens to the worker/thread?
   - The decorated function is async. Does validation run on the event loop or off it? Trace it.
   - A regex-based rule receives a pathological pattern or input. What protects against runaway
     execution?
   - Credentials are missing or malformed. Does the system fail loud or silently proceed?
   - Two requests arrive concurrently. Where are the shared mutable structures, and what protects
     them?
For each branch, cite the file and construct, and classify: CORRECT / PARTIAL / BROKEN / ABSENT,
with a one-paragraph human explanation of the consequence.

STEP 5 — RECONCILE AGAINST INTENT (build vs. spec vs. prior findings)
If any of these exist in the repository or have been provided, reconcile the code against them and
note every divergence: the SRS, any gap-analysis documents, any prior audit reports, any roadmap or
blueprint. For each, state: what the document says should exist, what the code actually does, and
where they differ. If the code is MORE correct than the spec (e.g., synchronous in-process
validation for latency rather than a naive async/queue approach), say so and recommend the spec be
updated — do not "fix" the code toward a worse spec. If prior audit findings exist, verify for each
whether it is STILL PRESENT, PARTIALLY FIXED, or RESOLVED in the current code, by reading the code,
not by trusting the audit.

STEP 6 — ASSEMBLE THE WHOLE (only now, the full-system picture)
Having understood the seams, the main path, and the branches, now explain the system AS ONE MACHINE:
how all the parts cooperate to deliver the product's purpose. Produce:
   - A full-system narrative (2–4 pages of prose): the complete story of the system, readable by
     someone who has never seen the code, that leaves them able to reason about it.
   - A master architecture diagram (component-level) WITH a prose legend explaining every box and
     every arrow in human terms.
   - The definitive FILE-TO-FILE LINKAGE MAP: for each file, what depends on it and what it depends
     on, presented so the founder can trace any path by hand.

STEP 7 — DIVIDE INTO PROBLEM PHASES (so the founder is never lost again)
Based on everything above, divide the remaining work into clearly-bounded PHASES, where each phase
is a coherent problem area (not a date). For each phase, state: the problem it addresses, why it
matters to the product's purpose, which existing files it will touch, what "done" means for it, and
its dependency on other phases. Order them by what must be trustworthy first. This becomes the
founder's map of the road ahead. Keep phases conceptual and stable — they are referenced by the
daily tracker (Document 3), so name them clearly and consistently.

OUTPUT FILES (create these; do not write code)
Write your findings to the following files at the repository root (create the directory
docs/system-analysis/ if helpful). Use clear Markdown. These are the durable artifacts:

1. docs/system-analysis/00_SYSTEM_MAP.md
   The master document: Steps 2, 3, and 6 (seams, primary-path narrative, full-system narrative +
   master diagram + linkage map). This is the file the founder reads to understand the whole system.

2. docs/system-analysis/01_FILE_INVENTORY.md
   Step 1 (the complete per-file inventory and inter-file import map).

3. docs/system-analysis/02_FAILURE_PATHS.md
   Step 4 (every branch and failure path, classified CORRECT/PARTIAL/BROKEN/ABSENT with consequences).

4. docs/system-analysis/03_SPEC_RECONCILIATION.md
   Step 5 (build vs. spec vs. prior findings; current status of each prior audit item).

5. CONGINE_PROGRESS.md  (at repository root — THE SHARED SOURCE OF TRUTH)
   Create or UPDATE this file. It must contain, in this order:
     a. A "SYSTEM STATE AS OF <date>" section summarizing, in human prose, what is built and
        trustworthy, what is built but broken, and what is absent. Keep this current — overwrite the
        prior state section when you re-run, but preserve the dated daily log below it (see below).
     b. A "PHASES" section: the conceptual phase breakdown from Step 7, each with its done-criteria.
        These phase names are the stable anchors the daily tracker references.
     c. A "DAILY LOG" header, below which Document 3 will append dated entries. If a DAILY LOG
        section already exists with entries beneath it, DO NOT erase those entries — preserve them
        and only refresh the SYSTEM STATE and PHASES sections above the log.

RE-RUN BEHAVIOR (this prompt is used repeatedly)
When this prompt is run again later:
   - Re-read the codebase fresh (do not trust your previous output — the code has changed).
   - Regenerate files 1–4 completely.
   - In CONGINE_PROGRESS.md, refresh the SYSTEM STATE and PHASES sections to reflect new reality,
     but PRESERVE the DAILY LOG entries beneath the log header. Note in the new SYSTEM STATE what
     changed since the previous state if a previous state is recorded.

FINAL CHECK BEFORE YOU FINISH
   - Did you actually open and read every source file? If any were skipped, list them and read them.
   - Is every architectural claim traceable to code you read?
   - Could the founder, reading 00_SYSTEM_MAP.md alone, trace a request through the system by hand?
   - Did you avoid modifying any source code?
   - Did you preserve any existing DAILY LOG entries in CONGINE_PROGRESS.md?
If any answer is no, fix it before declaring done.

=== PROMPT END ===
```

---

### Notes for you (the founder) — not part of the prompt

- **Run this first, before Document 3.** It establishes `CONGINE_PROGRESS.md` and the phase breakdown that the daily tracker depends on. If you run the daily tracker first, it won't have a phase map to anchor to.
- **Re-run it after each major problem area** (after you finish the integration/choke-point work, after the token-cascade work, etc.). It will refresh the system map and tell you what changed, while keeping your daily history intact.
- **It writes, it doesn't edit.** This prompt is deliberately read-only on your source. It cannot break your code; it can only produce understanding. That's by design — analysis and modification are different jobs and must not be mixed.
- **If it reports paths different from `libs/congine-sdk/`,** that's fine and expected — Step 0 makes it self-correct to your real layout. The path in the prompt is a sensible default, not a hard assumption.
- **The single most valuable output** is `00_SYSTEM_MAP.md` and specifically its file-to-file linkage map and primary-path narrative. That is the thing you've been missing — the human-form explanation of how your own system actually fits together.