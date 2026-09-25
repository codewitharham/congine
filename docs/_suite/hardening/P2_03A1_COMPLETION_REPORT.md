# P2-03a1 LangChain Representation Completeness — Completion Report

This is the engineering closure record for P2-03a1. Every figure below was produced by running the
repository gates on the P2-03a1 working tree. Baseline figures come from the same commands run on
`main @ 8c76945`. No number was predicted in advance.

---

## Status

| | |
|---|---|
| Milestone | **P2-03a1 — LangChain representation completeness & enforcement propagation** |
| Verdict | **Implementation complete; all P2-03a1 gates green** (one pre-existing gate gap, see [Baseline gap](#baseline-gap-evidence-trust)) |
| Baseline | `main @ 8c76945d31e1274f9412defb7c27e7675419420a` |
| Branch | `hardening/p2-03a1-langchain-representation` |
| Commit | not yet committed when this report was written |
| Specification | [`P2_03A1_IMPLEMENTATION_SPEC.md`](P2_03A1_IMPLEMENTATION_SPEC.md) (frozen; §1 and §22 amended before coding) |
| Local environment | Windows 11, Python 3.14.6, `langchain-core` 0.3.86 (pin `>=0.3,<0.4` unchanged) |

---

## What was wrong at baseline

1. **Clipping.** A stream longer than `max_stream_buffer_chars` was cut at the limit, and the prefix
   was validated as if it were the whole output.
2. **The final response was ignored.** When any token had been streamed, the final `LLMResult`
   was never inspected, so tool calls, extra candidates and truncation in the final result went
   unseen.
3. **Lossy extraction.** `_extract_text` read `generations[0][0]` and ignored everything else.
   When it could not extract text it returned `""`, which was then *evaluated*.
4. **Aliased run state.** `run_id=None` was a shared dictionary key.
5. **Swallowed enforcement.** `raise_error` was inherited as `False`, so LangChain's
   `CallbackManager` logged and swallowed every exception the handler raised, including a strict
   `CongineValidationError`. The mutation check below reproduces this: with `raise_error = False`,
   LangChain logs `Error in CongineCallbackHandler.on_llm_end callback: CongineValidationError(...)`
   and the host continues.

## What P2-03a1 established

The handler now evaluates only output it can establish as **completely represented**. That means
exactly one generation group holding exactly one generation. The generation's content must be a
plain string with no populated action or side channel, and its termination reason must be known
to mean "complete". A stream must end with a final `LLMResult` whose text equals the streamed
tokens. Everything else raises `CongineUnsupportedRepresentationError` before
`ValidateContractUseCase.execute()` is called. The refusal produces no `ValidationResult`, no
telemetry event, and nothing in `result_for(run_id)`. `raise_error = True` carries that refusal,
and a strict BLOCK, through LangChain's real dispatch.

Three consistency rules hold:

- `generation.text` must equal `message.content`
- each stream token must equal its chunk's text
- the joined stream text must equal the final text

### Production delta

| File | Change |
|---|---|
| `src/congine_core/exceptions.py` | New canonical Tier-1 `CongineUnsupportedRepresentationError(CongineBaseException)`. It is not an alias. |
| `src/congine_core/__init__.py` | Re-exports the new exception in the root `__all__`. |
| `src/congine_core/adapters/langchain_handler.py` | Rewritten around a private representation boundary; details below. |

The handler rewrite contains:

- a `_RunState` per run (replacing `_buffers`/`_buffer_lengths`)
- sticky refusal that keeps the first reason and clears retained text
- a refuse-never-clip buffer bound
- strict final-response extraction
- termination classification
- `raise_error = True`
- one sanitized public raise per callback

Unchanged, verified by `git diff main`: `domain/`, `usecases/`, `models.py`, `config.py`,
`security_limits.py`, `adapters/__init__.py`, `ports/`, `infrastructure/`, `tools/`, every
`pyproject.toml`, both `uv.lock` files, and `project.json`.

### Design points reviewers should know

- **The boundary rule.** Every helper that touches host objects re-raises a specific private
  refusal unchanged. It maps only *unexpected* host failures to that helper's fallback reason
  (`_guarded`). So a tool call in a stream chunk reports `tool_or_action_content`, never the
  generic `unsupported_stream_chunk`.
- **A sanitized public boundary.** `on_llm_new_token` and `on_llm_end` each raise the public
  error in exactly one place, outside the `except` block and `from None`. As a result
  `__cause__` and `__context__` are both `None`, and a hostile host's exception text never
  reaches callers, tracebacks, or LangChain's `repr(exc)` warning. The private refusal still
  keeps the host cause for in-module diagnostics.
- **Lock ownership.** `self._lock` is a plain `threading.Lock`, and no code path acquires it
  twice. `_refuse_locked` requires the caller to already hold it; `_mark_refused` is the only
  refusal helper that takes it. Inspection of host objects and the policy call both run outside
  the lock.
- **Termination classification.** Termination is read from `finish_reason` or `stop_reason` in
  four places: `generation_info`, `response_metadata`, top-level `llm_output`, and stream chunks.
  Values are normalized with `strip().lower()`; enums use `.value` when it is a string, else
  `.name`.

  | Class | Values | Outcome |
  |---|---|---|
  | known complete | `stop`, `end_turn`, `stop_sequence` | accepted |
  | truncated | `length`, `max_tokens`, `max_output_tokens` | `output_truncated` |
  | incomplete | `content_filter`, `safety`, `refusal` | `output_incomplete` |
  | anything else that isn't empty | — | `unknown_termination` |
  | a value of an unknown type | — | malformed refusal |

  An empty value or `None` means no signal.
- **The `llm_output` rule.** Only top-level keys are interpreted. Action keys (`tool_calls`,
  `invalid_tool_calls`, `tool_call_chunks`, `function_call`) and termination keys refuse. Every
  other key (`token_usage`, `model_name`, `system_fingerprint`, …) is provider metadata outside
  the governed text subject. This report makes no claim that it covers all provider metadata.
- **`additional_kwargs`.** Any populated value refuses: `tool_or_action_content` for
  `function_call` and `tool_calls`, `unsupported_message_metadata` for any other key. `None` and
  empty values count as absent, so OpenAI's `{"refusal": None}` passes.

---

## Closure checklist (spec §52)

Unit-test IDs refer to `tests/unit/test_langchain_handler.py`; `LC*` refers to
`tests/integration/test_langchain_callback_manager.py`.

| # | Criterion | Witness | Result |
|---|---|---|---|
| 1 | Complete plain final text can be evaluated | U01, U02, LC01, LC06b | ✅ |
| 2 | Complete textual streaming can be evaluated | U03, LC06 (real `GenericFakeChatModel.stream`), E2E `test_langchain_handler_through_real_container` | ✅ |
| 3 | Streaming requires a compatible final representation | U21, U22, U23 | ✅ |
| 4 | Multiple generations are refused | U16, LC02, E2E `test_langchain_unsupported_representation_emits_no_telemetry` | ✅ |
| 5 | Multiple generation groups are refused | U15 | ✅ |
| 6 | Structured/multimodal content is refused | U17 (LangChain's own `.text` flattening is shown and rejected), U18, list-token test, `test_refused_chat_generation_has_no_validation_result` | ✅ |
| 7 | Tool/action side channels are refused | U19, U20, U21, stream-chunk tool test, `llm_output` action-key test, LC04, LC07, LC08, LC09 | ✅ |
| 8 | Unsupported stream observations are sticky | U10, U11 (first reason kept against a later different refusal), U11a | ✅ |
| 9 | Local stream overflow refuses rather than clips | U07 (exactly 500 000 accepted), U08 (500 001 refused), U09 (a partly-fitting token is not clipped) | ✅ |
| 10 | Observable truncation refuses | U24, U25, the termination matrix across all four locations, stream-chunk truncation | ✅ |
| 11 | Stream/final mismatch refuses | U22 | ✅ |
| 12 | Missing final response after streaming refuses | U23 | ✅ |
| 13 | Explicit empty text is distinguished from absent or unrepresentable text | U04 (evaluated) against `test_missing_final_response_refuses_without_stream` and `test_non_string_plain_generation_text_refuses` | ✅ |
| 14 | Invalid run identity cannot alias state | U12, U13, `test_hostile_run_identity_is_a_sanitized_refusal` (hash failure at admission *and* on later use) | ✅ |
| 15 | Representation refusal calls `ValidateContractUseCase` zero times | `_assert_not_evaluated` in every refusal test; LC02/LC04/LC07–LC09 publish 0 events | ✅ |
| 16 | Representation refusal creates no `ValidationResult` | U29, `result_for(run_id) is None` throughout | ✅ |
| 17 | Representation refusal creates no validation telemetry event | E2E refusal test (0 events on a real container), LC02 | ✅ |
| 18 | Raw unsupported content never enters logs | U36, LC02 (LangChain's own WARNING captured), `_assert_sanitized` in all host-failure tests | ✅ |
| 19 | Direct `CongineBaseException` behavior remains intact | U30, U31, U33, U34 | ✅ |
| 20 | Representation refusal propagates through the real `CallbackManager` | LC02, LC04, LC07, LC08 (async), LC09; mutation check below | ✅ |
| 21 | Strict policy BLOCK propagates through the real `CallbackManager` | LC03 (real container, `FailMode.STRICT`, one event, then `CongineValidationError`) | ✅ |
| 22 | Concurrent runs remain isolated | U06 (two tests), `test_refusing_one_run_does_not_touch_concurrent_runs`, `test_completed_results_are_consistent_under_concurrency` | ✅ |
| 23 | Lifecycle semantics remain intact | U33, U34, `test_closed_container_rejects_error_callback_before_state_mutation` | ✅ |
| 24 | Optional LangChain import remains lazy | `test_importing_the_sdk_does_not_import_langchain` (subprocess), `test_lazy_adapter_export` | ✅ |
| 25 | Architecture gate remains zero-exemption | `congine-sdk:architecture`: 42 files, 90 tests, no allowlist change | ✅ |
| 26 | No dependency version changes | `git diff --exit-code main` over both `pyproject.toml`s, both `uv.lock`s, `project.json`: clean | ✅ |
| 27 | No domain/use-case/result-model changes | `git diff --stat main` over the protected paths: empty | ✅ |
| 28 | Existing P0/P1/P1.5 evidence remains green | `tools.p0_evidence`: 5/5 properties hold; `tools.p1_5_evidence capability`: intact; full suite green | ✅ |

### Propagation mutation check

`raise_error` was forced back to `False` in-process, and the real-dispatch module was re-run.
Eight tests failed:

- LC02, LC03, LC04, LC05, LC07, LC08, LC09
- `test_refused_chat_generation_has_no_validation_result`

Only the three pass-path tests (LC01, LC06, LC06b) still passed. The integration tests therefore
detect the baseline defect; they don't merely coexist with it.

---

## Gate results

| Gate | Baseline (`8c76945`) | P2-03a1 |
|---|---|---|
| Targeted (`test_langchain_handler`, `test_langchain_callback_manager`, `test_end_to_end`) | 32 passed (21 unit + 11 E2E; no CallbackManager module) | **228 passed** (205 + 11 + 12) |
| `congine-sdk:lint` | — | **pass** (118 files formatted; ruff clean) |
| `congine-sdk:typecheck` (mypy strict) | — | **pass** (42 source files) |
| `congine-sdk:architecture` | — | **pass** (42 source files; 90 tests) |
| `congine-sdk:examples` | pass | **pass**; now also exercises the streamed reply |
| `congine-sdk:test` | 823 passed, 1 skipped | **1019 passed, 1 skipped** |
| `congine-sdk:coverage`, total | 91% | **92%** |
| `congine-sdk:coverage`, `langchain_handler.py` | 77% (140 statements) | **94%** (339 statements) |
| `tools.p0_evidence` | — | **5/5 properties hold** |
| `tools.p1_5_evidence capability` | — | **intact** |
| `congine-sdk:evidence-trust` | fails (see below) | fails at the same pre-existing step |
| `git diff --check` | — | **clean** |

The skipped test is `tests/adversarial/test_remediations.py:203` ("symlinks not permitted on this
platform/user"), a Windows permission skip unrelated to P2-03a1. The 3 warnings are
`DeprecationWarning`s raised inside `langchain_core/callbacks/manager.py:376` under Python 3.14
(`asyncio.iscoroutinefunction`), not in SDK code.

The handler lines still uncovered all predate this change:

- the constructor's `ImportError` and default-container paths
- `_ensure_open`'s non-Congine-exception branch
- `on_llm_error`'s `CongineBaseException` branch
- the logger-absent branches
- `_best_effort_record_failure`'s swallow

Every new representation branch is covered.

### Baseline gap: `evidence-trust`

`project.json`'s `evidence-trust` target runs `tools.p2_evidence golden --check` and
`tools.p2_evidence inventory --check`, but `libs/congine-sdk/tools/p2_evidence/` does not exist
at the baseline commit. The target's first two commands pass. The third fails with
`No module named tools.p2_evidence`, exactly as it does on `main`. CI does not run this target.
P2-03a1 neither causes nor repairs this; it needs its own change.

### Repository hygiene note

The workspace-root `.coverage` data file is tracked in git, so every coverage run modifies a
tracked file. It was restored from `main` after each run and is not part of this change. It
should probably be untracked and ignored in a separate change.

---

## Deviations from the specification

All of these were approved during plan review before implementation.

1. **Spec §28 `from exc` is replaced by a sanitized public boundary (`from None`).** Host
   causality stays on the private refusal and is never exposed publicly.
2. **Four reasons were added:**
   - `TEXT_MESSAGE_MISMATCH` (§19)
   - `OUTPUT_INCOMPLETE` (known early stops that aren't length limits)
   - `UNKNOWN_TERMINATION` (fail-closed termination classification)
   - `STREAM_TOKEN_CHUNK_MISMATCH` (token/chunk consistency)
3. **Termination is classified against an allowlist**, not just checked for truncation.
   `LLMResult.llm_output` is inspected, per the §1/§22 amendment.
4. **`additional_kwargs` treats `None` and empty values as absent**; any populated value refuses.
5. **Refusals are logged by reason code:** message `"LangChain output representation refused"`
   with `contract_id`, `error_type` and `reason`. §29 allowed this but did not require it.
6. **Tests beyond the U01–U36 / LC01–LC05 matrix:**
   - U11a
   - LC06, LC06b, LC07, LC08, LC09
   - the parser-hardening, termination-matrix and sanitization witnesses
   - the lock-release regression guard
   - the lazy-import subprocess check
7. **`smoke.py` now runs the streamed reply.** The example's streaming step moved into
   `agent.stream_support_reply()`, which `smoke.py` asserts. Without this the `examples` gate
   never exercised the changed code.
8. **Run-identity hardening goes beyond §14.** Any exception from `hash(run_id)` refuses, not
   just `TypeError`. A run ID that passes admission but whose hash or equality fails on a later
   state lookup is also refused as `unhashable_run_id`.

## Known limits

- **There are two cleanup paths, by design.** A direct caller that catches a streaming refusal
  leaves the run `REFUSED` until `on_llm_end` or `on_llm_error` (U11a). Under real LangChain
  dispatch, LangChain calls `on_llm_error` with the refusal before re-raising, which clears the
  run (LC09).
- **Some ordinary provider values now refuse, on purpose:**
  - populated `reasoning_content`-style `additional_kwargs`
  - normal stop values outside the small allowlist (e.g. `tool_use`, `eos_token`, `COMPLETE`)

  Each needs an explicit classification before it can pass.
- **`llm_output` is not searched recursively.** Only top-level action and termination keys are
  read.
- **Late identity failures are handled by the existing containment.** If a run ID's hashing
  fails only when the result is being recorded, the one evaluation has already happened and the
  existing use-case containment returns `None` (spec §27, unchanged). CPython doesn't hash a key
  when popping from an empty dict, so such an ID can get past the refusal checks. A strict
  BLOCK still raises before result bookkeeping.

## Documentation updated

- `libs/congine-sdk/README.md`: the "LangChain callback behavior" section, and the
  `max_stream_buffer_chars` row ("refused, never clipped").
- `libs/congine-sdk/examples/LangChain/README.md`: rows B and C, and §3.
- `docs/architecture/ARCHITECTURE_CURRENT.md`:
  - the module table row and boundary-check paragraph
  - §9.5 rows 49 and 50 rewritten; rows 50a and 50b added
  - the lock inventory (row 8) and state inventory (rows 18 and 19)
  - an F3 status note
  - config row 44
  - the limits table and its fail-closed sentence
- `docs/architecture/AUDIT_ID_INDEX.md`: a `P2-*` series with the `P2-03a1` row.
