# P1.5 Slice A0 — Semantic Capability Falsification

**Purpose.** Independently verify — not assume — the additional hypotheses raised in adversarial
review, before any budget, complexity or caching work begins. Every claim below was produced by a
black-box witness against the real evaluator. **No production code was modified in A0.**

| | |
|---|---|
| Branch | `P1_5_SEMANTIC_SAFETY` (from `e59fece`) |
| P1 engineering baseline | `b482bc4` (immutable) |
| jsonschema | 4.26.0 · `referencing` 0.37.0 (transitive) |
| Python / OS | 3.14.6 / Windows 11 |
| Drafts exercised | draft4, draft6, draft7, 2019-09, 2020-12 |

Governing rule applied: *a confirmed claim is a P1.5 trust blocker; a claim that does not reproduce
gets no speculative fix.*

---

## Verdict summary

| # | Hypothesis | Verdict | Severity |
|---|---|---|---|
| A0-1 | Semantic `pattern`/`patternProperties` reach Python backtracking `re` | **CONFIRMED** | **BLOCKER** |
| A0-2 | External `$ref` triggers implicit retrieval | **CONFIRMED — real network fetch** | **BLOCKER** |
| A0-3 | `contentEncoding` / `contentMediaType` admitted but not enforced | **CONFIRMED, all 5 drafts** | **BLOCKER (G12)** |
| A0-4 | `format` admitted but unenforceable for unknown format names | **CONFIRMED (conditional)** | **G12 gap** |
| A0-5 | Missing / cyclic local `$ref` admitted, then errors at evaluation | **CONFIRMED** | G12 gap |
| A0-6 | Unknown keywords silently admitted | **DID NOT REPRODUCE** — admission correctly refuses | none |
| A0-7 | `format` admitted while checker disabled | **DID NOT REPRODUCE** — admission correctly refuses | none |

Two hypotheses did not reproduce. Per the governing rule, **no fix will be written for A0-6 or
A0-7** — the existing P0 admission logic is already correct there.

---

## A0-1 — Regex engine (BLOCKER)

**Source-verified.** `jsonschema._keywords.pattern` is:

```python
def pattern(validator, patrn, instance, schema):
    if (validator.is_type(instance, "string") and not re.search(patrn, instance)):
        yield ValidationError(...)
```

`re` is CPython's **backtracking** engine. `patternProperties` likewise. By contrast CONGINE's
native `RuleEngine` uses **`re2`**. The same keyword is therefore linear-time natively and
exponential semantically — an asymmetry no user is told about.

**Exploitability — measured** (`^(a+)+$` against `"a"*n + "!"`):

| input length | 16 | 20 | 22 | 24 | 26 |
|---|---|---|---|---|---|
| match time | 7.6 ms | **104.8 ms** | 450.1 ms | 1 837.8 ms | **7 688.6 ms** |

Exponential; passes the entire 100 ms default budget at n=20. Other catastrophic shapes measured on
the main thread: `^(a+)+$` 3 337 ms, `^(a|a?)+$` **31 466 ms**.

**The budget does not contain it.** Through the real stack
(`BoundedValidationExecutor` → `CompositeValidator` → semantic), budget 100 ms, two fresh processes:

```
run 1: TimeoutError after 2008.6 ms      (deadline enforced 20x late)
run 2: returned NORMALLY after 2179.1 ms (deadline never fired at all)
```

**Why:** `re.search` holds the GIL for the whole match — a probe thread recorded **0 main-thread
wakeups** during a 1 802 ms match, versus 128 wakeups during a control `time.sleep(2)`. A waiter
cannot observe its own deadline while a C-level regex holds the GIL. And even when `TimeoutError`
does fire, the work is **not cancelled**: the worker and its permit remain occupied until the match
completes (documented executor behaviour — the permit is released by a done-callback).

So a single adversarial contract+payload pair occupies a validation worker for seconds. This is
precisely the founder's stated blocker condition: *a thread timeout is not cancellation of runaway
regex execution.*

*Not carried forward:* one alternation-pattern probe showed an anomalous 0.01 ms worker-thread
result that did **not** reproduce with the plain pattern (worker 2 757 ms vs main 3 133 ms — in
agreement). No claim is built on it, and no false-negative disagreement was observed: matching and
non-matching inputs agreed on both threads.

## A0-2 — External reference retrieval (BLOCKER)

**Confirmed by direct observation, not inference.** A local HTTP server was started and a contract
pointed a `$ref` at it:

```
validation completed in 73.9 ms -> 1 breach
   breach: '...' is not of type 'number'
*** SERVER HITS: 1  paths=['/remote-schema.json'] ***
```

**CONGINE fetched a remote schema over the network and enforced the payload against it.** The
remote document therefore *controls policy*. Consequences: enforcement becomes non-deterministic
and remotely mutable, an outbound request occurs inside the validation budget with unbounded
latency, and a governance SDK gains an SSRF vector. `jsonschema` itself emits:

> *DeprecationWarning: Automatically retrieving remote references can be a security vulnerability
> and is discouraged by the JSON Schema specifications … will shortly become an error.*

An initial socket-level probe suggested "no retrieval"; that was a **false negative in my own
harness** — interception at `urllib.request.urlopen` recorded **10 attempts** across drafts. The
finding was only settled by the live-server witness. Retrieval is attempted on **all five drafts**
for `http:`, `file:` and relative-external refs.

**Fix proven before adoption.** A `referencing.Registry` whose `retrieve` raises `NoSuchResource`:

| | server hits | outcome |
|---|---|---|
| current behaviour | **1** | remote schema fetched and enforced |
| with no-retrieval registry | **0** | fails closed (`_WrappedReferencingError`) |
| local `#/$defs/...` ref, with registry | 0 | **still enforced** (1 breach) — no capability lost |

### Runtime dependency — conditional approval triggered

The founder pre-approved declaring `referencing` **only if** falsification proved a no-retrieval
policy necessary *and* the supported API requires it. Both conditions are now met. Recorded as
required:

| Item | Finding |
|---|---|
| Why necessary | Only `Registry(retrieve=…)` disables implicit retrieval; there is no jsonschema-level switch |
| Supported API used | `referencing.Registry`, `referencing.exceptions.NoSuchResource`, and the `Validator(schema, registry=…)` kwarg (confirmed present) |
| Current transitive version | **0.37.0**, already installed via `jsonschema>=0.28.4` |
| `jsonschema` re-export? | **No** — `hasattr(jsonschema, "Registry")` is `False`, so a direct import is unavoidable |
| Lockfile impact | None expected: already in the resolved graph; declaring it pins an existing node rather than adding one |
| Security / determinism reason | Removes an SSRF vector and makes enforcement independent of network state and remote mutation |

Declaring it makes an already-present transitive package an explicit, version-constrained contract.

## A0-3 — `contentEncoding` / `contentMediaType` (BLOCKER, G12)

Admission composes these into the enforced set via `SEMANTIC_ENFORCED_KEYWORDS`, so a contract using
them is **admitted**. The evaluator treats them as **annotations only** — measured on **all five
drafts**, an invalid value produces **zero** breaches:

```
draft4 / draft6 / draft7 / 2019-09 / 2020-12
  contentEncoding   -> ANNOTATION ONLY (silent pass)
  contentMediaType  -> ANNOTATION ONLY (silent pass)
```

This is a direct **G12 violation**: admission advertises policy-activation truth it cannot deliver,
and the clause silently enforces nothing. It matches the founder's rule that *keywords which are
annotations rather than enforced assertions must not be advertised by admission as enforced.* This
is also correct per spec — both are annotation-only in 2019-09+.

## A0-4 — `format` truth (G12 gap, conditional)

| condition | admitted? | enforced? |
|---|---|---|
| `format_checking` **off** | **No** (correctly refused) | n/a |
| `format_checking` on, **known** format (`email`) | Yes | **Yes**, all 5 drafts |
| `format_checking` on, **unknown** format (`unknown-xyz`) | Yes | **No — silent pass**, all 5 drafts |

The existing P0 design is right about the *flag* (A0-7 did not reproduce), but wrong about
*granularity*: `format` is admitted wholesale, so an unrecognised format name is admitted and then
silently unenforced. Admission must consult the **concrete configured checker** for the **specific
format name**.

## A0-5 — Local reference integrity (G12 gap)

| case | admitted? | evaluation |
|---|---|---|
| valid local `#/$defs/S` | Yes | **enforced correctly** |
| missing local target | **Yes** | `_WrappedReferencingError` at evaluation |
| cyclic local `$ref` | **Yes** | `RecursionError` at evaluation |

Both fail *closed* at runtime (surfacing as degraded `internal_error` / `resource_error`), so G14 is
not breached — but admission claimed enforceability it cannot deliver, so **G12 is**. These are
statically detectable at admission time.

---

## What A0 authorises for Slice B

Confirmed, therefore in scope:

1. **RE2-backed semantic pattern path**, draft-preserving, with the founder-specified test matrix.
2. **Explicit no-retrieval reference policy**, with `referencing` declared under the recorded
   conditional approval; verified local JSON-pointer refs remain supported.
3. **Admission capability truth**: drop `contentEncoding`/`contentMediaType` from the enforced set;
   make `format` checker-and-name aware; reject missing/cyclic local refs at admission.

Not reproduced, therefore **explicitly not implemented**: unknown-keyword admission (A0-6) and
format-while-disabled (A0-7).

Out of scope and unchanged: `schema_storage.put()` universal admission,
`AdmittedContract`/`CompiledContract`, version-aware storage identity, full three-axis result model.
Fixing reference *retrieval* does **not** address version-aware storage identity and must not be
described as doing so.
