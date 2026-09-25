# P2-03a1 Implementation Specification

- **Milestone:** P2-03a1 — LangChain Representation Completeness & Enforcement Propagation
- **Repository baseline:** `main @ 8c76945d31e1274f9412defb7c27e7675419420a`
- **Status:** FROZEN — approved for implementation (amendments to §1 and §22 applied before coding)
- **Scope:** LangChain L5 adapter only, plus the minimum L0 exception/public-surface/test/example/documentation changes required to make the boundary truthful.

---

## 1. Milestone objective

P2-03a1 closes one specific false-safety path:

> **CONGINE must not evaluate or certify a LangChain output unless the adapter can establish that the governed output has been completely and faithfully represented under supported semantics.**

The property is:

```text
complete + supported representation
                ↓
        policy evaluation
                ↓
       deterministic verdict
```

versus:

```text
partial / ambiguous / unsupported
                ↓
              REFUSE
                ↓
     zero policy evaluations
```

The second half of the milestone is equally important:

> **If CONGINE refuses an output or makes an enforcing BLOCK decision, that exception must survive LangChain's real callback dispatch path.**

This is an adapter-integrity milestone, **not** a LangChain upgrade, policy-engine rewrite, multimodal feature, or agent-action governance expansion.

> **Amendment (approved before implementation):** Observable LangChain metadata may be outside the governed textual subject, but it may not be ignored when it changes whether that subject is known to be complete.

---

# 2. Supported semantics after P2-03a1

P2-03a1 deliberately supports a narrow representation.

### Supported

**Non-streaming**

Exactly one generation group containing exactly one generation whose governed content is completely representable as a string.

```text
LLMResult
└── generations[0]
    └── generation[0]
        └── complete text
```

**Streaming**

A sequence of supported text observations that:

1. never becomes unsupported,
2. never exceeds the local stream bound,
3. ends with an inspectable final response,
4. and whose accumulated text agrees with the final represented text.

### Explicitly unsupported

P2-03a1 must refuse rather than partially govern:

- multiple generation groups,
- multiple candidate generations,
- list/structured message content,
- multimodal content,
- image-only output,
- tool calls,
- function calls,
- action-bearing message side channels,
- unsupported streaming observations,
- streams exceeding the configured buffer,
- observable provider/model truncation,
- malformed response shapes,
- stream/final-response disagreement,
- missing final response after streaming,
- output whose complete representation cannot be established.

This milestone does **not** attempt to add deterministic semantics for those forms.

---

# 3. Exact production files

| File | Action | Purpose |
|---|---|---|
| `libs/congine-sdk/src/congine_core/adapters/langchain_handler.py` | **Major modification** | Representation state, strict extraction, refusal, sticky stream state, real callback propagation |
| `libs/congine-sdk/src/congine_core/exceptions.py` | **Small modification** | Add canonical representation-refusal exception |
| `libs/congine-sdk/src/congine_core/__init__.py` | **Small modification** | Export the new canonical exception |
| `libs/congine-sdk/src/congine_core/adapters/__init__.py` | **NO CHANGE** | Existing lazy LangChain exposure remains correct |
| `libs/congine-sdk/src/congine_core/security_limits.py` | **NO CHANGE** | Existing 500,000-character limit remains |
| `libs/congine-sdk/src/congine_core/config.py` | **NO CHANGE** | Existing `max_stream_buffer_chars` configuration remains |

I recommend one deliberate public addition:

```python
class CongineUnsupportedRepresentationError(CongineBaseException):
    """The host output cannot be completely represented under supported semantics."""
```

Add it to:

```python
exceptions.__all__
```

and the root:

```python
congine_core.__all__
```

Do **not** alias it to `CongineValidationError`.

A representation refusal is not a policy breach.

---

# 4. Exact test/example files

| File | Action |
|---|---|
| `libs/congine-sdk/tests/unit/test_langchain_handler.py` | Expand substantially / replace assumptions that permit partial representation |
| `libs/congine-sdk/tests/integration/test_langchain_callback_manager.py` | **NEW** — prove behavior through real LangChain callback dispatch |
| `libs/congine-sdk/tests/integration/test_end_to_end.py` | Update LangChain E2E to use a complete final response and add zero-evaluation refusal witness |
| `libs/congine-sdk/examples/LangChain/agent.py` | Update manual streaming example to provide a real final `LLMResult` matching the stream |
| `libs/congine-sdk/examples/LangChain/smoke.py` | Change only if needed to keep the example gate valid |

The existing example currently does:

```python
for chunk in [...]:
    stream_protector.on_llm_new_token(chunk, run_id=session_id)

stream_protector.on_llm_end(run_id=session_id)
```

That should no longer be considered sufficient proof of a complete LangChain result.

The example should terminate with an inspectable final response.

---

# 5. Documentation files

Implementation specification:

```text
docs/_suite/hardening/P2_03A1_IMPLEMENTATION_SPEC.md
```

After code + evidence are green:

```text
docs/_suite/hardening/P2_03A1_COMPLETION_REPORT.md
```

Update relevant LangChain/boundary sections in:

```text
docs/architecture/ARCHITECTURE_CURRENT.md
```

only after the implementation has been verified.

The current architecture documentation says stream overflow is silently clipped. That statement must eventually change to the verified new behavior.

Do **not** invent `G17`.

Treat representation completeness as a P2-03a1 property until the invariant documentation is deliberately reconciled.

---

# 6. New internal representation model

Replace the parallel state:

```python
_buffers: Dict[Any, List[str]]
_buffer_lengths: Dict[Any, int]
```

with one state object per active run.

Recommended shape:

```python
@dataclass
class _RunState:
    parts: List[str]
    length: int
    status: _RunStatus
    refusal_reason: Optional[_RefusalReason]
```

with:

```python
class _RunStatus(Enum):
    COLLECTING_TEXT = "collecting_text"
    REFUSED = "refused"
```

The absence of an entry represents:

```text
NO ACTIVE RUN
```

There is no need to persist `ENDED` in `_runs`; the state should be removed when the callback ends.

---

# 7. Private refusal vocabulary

Keep detailed representation reasons private to the LangChain adapter.

For example:

```python
class _RefusalReason(Enum):
    MISSING_RUN_ID = "missing_run_id"
    UNHASHABLE_RUN_ID = "unhashable_run_id"

    NON_TEXT_STREAM_TOKEN = "non_text_stream_token"
    UNSUPPORTED_STREAM_CHUNK = "unsupported_stream_chunk"
    STREAM_BUFFER_EXCEEDED = "stream_buffer_exceeded"

    MISSING_FINAL_RESPONSE = "missing_final_response"
    MALFORMED_FINAL_RESPONSE = "malformed_final_response"
    NO_GENERATION = "no_generation"
    MULTIPLE_GENERATION_GROUPS = "multiple_generation_groups"
    MULTIPLE_GENERATIONS = "multiple_generations"

    NON_TEXT_CONTENT = "non_text_content"
    TOOL_OR_ACTION_CONTENT = "tool_or_action_content"
    UNSUPPORTED_MESSAGE_METADATA = "unsupported_message_metadata"

    OUTPUT_TRUNCATED = "output_truncated"
    STREAM_FINAL_MISMATCH = "stream_final_mismatch"
```

Names can be refined during implementation, but the categories must remain distinguishable in tests.

Do **not** put model output in the exception.

Acceptable:

```text
LangChain output cannot be governed safely:
unsupported representation (stream_buffer_exceeded)
```

Forbidden:

```text
Unsupported output: <actual model response here>
```

---

# 8. State machine

## Initial state

```text
ABSENT
```

No active representation state exists for the run.

---

## Valid text token

```text
ABSENT
  │ valid text token
  ▼
COLLECTING_TEXT
```

or:

```text
COLLECTING_TEXT
  │ valid text token
  ▼
COLLECTING_TEXT
```

The token is appended atomically under the current state lock.

---

## Unsupported observation

Examples:

- non-string token,
- unsupported chunk,
- local buffer overflow.

Transition:

```text
COLLECTING_TEXT
        │
        │ unsupported observation
        ▼
      REFUSED
```

or:

```text
ABSENT
   │ unsupported observation
   ▼
REFUSED
```

Once refused:

```text
REFUSED → REFUSED
```

always.

No later valid token may restore the run.

---

# 9. Sticky refusal rule

This is load-bearing.

Example:

```text
"text A"
   ↓
structured / unsupported chunk
   ↓
"text B"
```

The state must remain:

```text
REFUSED
```

not:

```text
"text Atext B" → evaluate
```

The **first refusal reason should remain authoritative**.

Subsequent observations must not overwrite it.

---

# 10. Payload retention after refusal

As soon as a run becomes `REFUSED`:

```python
state.parts.clear()
state.length = 0
```

Keep only:

```text
status
refusal_reason
```

This has two advantages:

1. there is no chance that already-collected text is accidentally evaluated later;
2. raw unsupported/model output is not retained unnecessarily.

---

# 11. Stream buffer semantics

Current behavior:

```python
remaining = max - current
clipped = token[:remaining]
append(clipped)
```

must be removed.

P2-03a1 behavior:

```text
current_length + incoming_length <= limit
        ↓
append full token
```

otherwise:

```text
current_length + incoming_length > limit
        ↓
REFUSE
```

Never:

```text
clip → validate prefix
```

If the limit is:

```text
500_000
```

then exactly `500_000` characters remain valid.

Character `500_001` causes refusal.

---

# 12. Immediate refusal propagation

When an unsupported observation is encountered during streaming:

1. mark the run `REFUSED`,
2. clear retained text,
3. raise `CongineUnsupportedRepresentationError`.

Example:

```python
handler.on_llm_new_token(non_text_content, run_id=rid)
```

should raise immediately.

The sticky state remains in case:

- the framework catches the exception unexpectedly,
- another callback still fires,
- or a direct caller catches it and continues.

If `on_llm_end()` subsequently occurs for that run, it must refuse again and must never call the use case.

---

# 13. LangChain exception propagation

`BaseCallbackHandler` defaults to behavior equivalent to:

```python
raise_error = False
```

CONGINE must override this.

Inside:

```python
class CongineCallbackHandler(_BaseCallbackHandler):
```

set:

```python
raise_error = True
```

This is preferable to depending on callers to configure it.

The security property is:

```text
CONGINE callback raises enforcing SDK exception
                ↓
LangChain CallbackManager receives exception
                ↓
exception propagates
                ↓
host cannot quietly continue
```

The test must exercise the **real `CallbackManager` path**, not merely:

```python
handler.on_llm_end(...)
```

directly.

---

# 14. Run identity semantics

The current use of:

```python
run_id=None
```

creates a shared dictionary key and therefore allows unrelated direct callback invocations to alias state.

P2-03a1 should refuse stateful governance without a valid run identifier.

For:

```python
on_llm_new_token()
on_llm_end()
```

require:

```text
run_id is not None
AND
hash(run_id) succeeds
```

Otherwise raise:

```text
CongineUnsupportedRepresentationError
```

with a sanitized reason.

Real LangChain dispatch supplies a real run ID, so this primarily removes an unsafe manual/direct-callback ambiguity.

---

# 15. Final-response extraction contract

Delete the current permissive semantic:

```python
_extract_text(response) -> str
```

where failure frequently becomes:

```python
""
```

Replace it with something conceptually closer to:

```python
_extract_complete_text(response) -> str
```

where inability to establish complete text **raises/refuses**.

Critical distinction:

```text
explicit text == ""
```

may be a valid complete output.

But:

```text
could not extract text
```

must never be converted to:

```text
""
```

These are different states.

---

# 16. Generation cardinality

The final response must satisfy:

```text
len(response.generations) == 1
```

and:

```text
len(response.generations[0]) == 1
```

Otherwise refuse.

Therefore:

```text
[[candidate_1, candidate_2]]
```

is unsupported.

And:

```text
[
  [prompt_1_generation],
  [prompt_2_generation]
]
```

is unsupported.

P2-03a1 does not decide which candidate is authoritative.

---

# 17. Plain completion representation

For a non-chat generation:

```text
generation.text
```

must be a string.

No silent fallback.

A proper:

```python
Generation(text="")
```

is complete textual output and may be evaluated.

A malformed generation with no supported text representation is refusal.

---

# 18. Chat message representation

For a chat generation, `message.content` must be a plain string.

Supported:

```python
AIMessage(content="Deploy completed.")
```

Unsupported:

```python
AIMessage(
    content=[
        {"type": "text", "text": "Deploy completed."},
        {"type": "image", ...}
    ]
)
```

even if a text portion can be extracted.

P2-03a1 must not flatten content blocks into a string.

---

# 19. Text/message agreement

If both are available:

```text
generation.text
message.content
```

and both are strings, they must agree.

If they disagree:

```text
REFUSE
```

Do not arbitrarily prefer one representation.

This eliminates another:

```text
"pick whatever field is easiest"
```

trust assumption.

---

# 20. Tool/action side channels

A textual message is not enough to establish completeness if the message also contains an action.

Example:

```text
content:
"The request looks safe."

tool_calls:
delete_customer_record(id=42)
```

must be:

```text
REFUSE
```

not:

```text
validate("The request looks safe.")
```

Inspect at minimum the known LangChain message fields relevant to agent action representation:

```text
tool_calls
invalid_tool_calls
tool_call_chunks
additional_kwargs
```

Non-empty action/function-call-bearing structures must refuse.

For P2-03a1, a conservative treatment of unaccounted message-side metadata is preferable to silently ignoring it.

---

# 21. Structured content

Any content representation other than a plain string must refuse in this milestone.

Examples:

```python
content=[...]
```

```python
content={"text": "..."}
```

```python
content=None
```

where another structure carries output.

Do not introduce a generic flattening algorithm.

That belongs to the later Governed Subject work.

---

# 22. Observable truncation

There are two different truncation sources.

### CONGINE truncation

If the local buffer would overflow:

```text
REFUSE immediately
```

### Provider/model truncation

If final/chunk metadata visibly reports an incomplete generation, such as known termination information representing:

```text
length
max_tokens
max_output_tokens
```

the output must refuse.

Inspect known termination fields such as:

```text
finish_reason
stop_reason
```

where present in the supported LangChain objects/metadata, including:

```text
generation.generation_info
message.response_metadata
LLMResult.llm_output        (amendment, approved before implementation)
stream chunk metadata
```

Do not attempt a provider-specific universal taxonomy in this milestone.

The requirement is:

> When truncation is observable, it must never be ignored.

---

# 23. Streaming final-response reconciliation

For a streamed run:

```text
streamed text
+
final response
```

must both be accounted for.

Do not keep current behavior:

```python
if streamed_text:
    ignore response
```

New behavior:

```text
collect complete supported stream
        ↓
inspect final response
        ↓
extract complete final text
        ↓
compare
```

If:

```text
stream_text == final_text
```

evaluation may proceed.

If:

```text
stream_text != final_text
```

refuse.

---

# 24. Missing final response

For a run in which streaming occurred:

```python
on_llm_end(response=None)
```

must refuse.

Reason:

the adapter cannot establish that the text-token stream represents the entire final model result or that no action-bearing final structure exists.

This intentionally changes the existing manual demo behavior.

---

# 25. Successful evaluation path

Only after complete representation has been established:

```python
payload = {
    self._payload_key: complete_text,
}
```

then:

```python
self._container.validate_contract_usecase.execute(
    payload=payload,
    contract_id=self._contract_id,
    contract_version=self._version,
)
```

There must be exactly one `execute()` call.

No preliminary policy call.

No policy call during extraction.

No call after refusal.

---

# 26. Refusal path

For any representation refusal:

```text
representation inspection
        ↓
REFUSED
        ↓
execute() call count == 0
        ↓
result_for(run_id) == None
        ↓
no fabricated ValidationResult
        ↓
raise CongineUnsupportedRepresentationError
```

This is not:

```text
status="fail"
```

and not:

```text
degraded=True
```

because no policy evaluation occurred.

---

# 27. Exception semantics

## `CongineUnsupportedRepresentationError`

Meaning:

> CONGINE cannot establish a complete supported governed representation for this host output.

It means neither:

```text
policy violated
```

nor:

```text
policy passed
```

nor:

```text
validation timed out
```

It represents:

```text
NO POLICY VERDICT WAS PRODUCED
```

---

## `CongineValidationError`

Unchanged.

Meaning remains an enforcing policy/validation failure after actual evaluation.

---

## Other `CongineBaseException`

Existing semantics remain:

```text
log safely
re-raise unchanged
```

---

## Unexpected non-CONGINE use-case exceptions

Do not redesign this policy in P2-03a1.

Current generic containment around unexpected use-case exceptions remains a separate concern unless implementation evidence proves it directly blocks P2-03a1 correctness.

Do not let this milestone turn into a full callback-failure-policy rewrite.

---

# 28. Representation parsing exceptions

There is one important exception to the previous boundary.

If an unexpected host-object error occurs **while trying to establish representation completeness**, for example:

```python
@property
def generations(self):
    raise RuntimeError(...)
```

that cannot remain:

```text
log → return None → host continues
```

because representation was not established.

Convert that boundary failure into:

```text
CongineUnsupportedRepresentationError
```

using exception chaining:

```python
raise CongineUnsupportedRepresentationError(
    "LangChain output representation could not be established."
) from exc
```

Do not include `str(exc)` in the public message or logs.

---

# 29. Logging semantics

Existing safe logging pattern is good:

```python
self._logger.error(
    "LangChain validation failed",
    contract_id=self._contract_id,
    error_type=type(exc).__name__,
)
```

No raw:

- prompt,
- response,
- token,
- tool parameters,
- metadata,
- generated code,
- structured content

may be logged by the adapter.

P2-03a1 tests must verify this.

An internal refusal reason code may be used in memory/tests, but adding it to production logging is not required for this milestone.

---

# 30. Cleanup semantics

On successful `on_llm_end`:

```text
active state removed
result recorded
```

On refusal:

```text
active state removed
per-run result removed
last_result cleared according to existing failure semantics
exception raised
```

On `on_llm_error`:

```text
active state removed
per-run result removed
partial output discarded
```

Do not evaluate partial output after an LLM error.

---

# 31. Thread-safety

Keep the existing single lock unless evidence proves it inadequate.

All transitions affecting:

```text
_runs
_results
_last_result
```

must remain lock-protected.

Expensive or host-object representation inspection should preferably happen outside the lock after active state is atomically detached, so unrelated runs do not block unnecessarily.

Do not introduce multiple locks in P2-03a1 without a demonstrated need.

---

# 32. Suggested flow for `on_llm_new_token`

Conceptually:

```python
def on_llm_new_token(token, *, run_id, **kwargs):
    ensure_open()

    key = require_run_id(run_id)

    try:
        inspect_stream_observation(token, kwargs.get("chunk"))
    except representation_problem:
        mark_refused(key, reason)
        raise CongineUnsupportedRepresentationError(...)

    with lock:
        state = get_or_create_run(key)

        if state.status is REFUSED:
            raise refusal(state.refusal_reason)

        if state.length + len(token) > max_buffer:
            refuse_state(state, STREAM_BUFFER_EXCEEDED)
            raise refusal(...)

        state.parts.append(token)
        state.length += len(token)
```

Exact factoring is implementation choice; semantic order is not.

---

# 33. Suggested flow for `on_llm_end`

Conceptually:

```python
ensure_open()
key = require_run_id(run_id)

state = detach_active_state(key)

if state is REFUSED:
    record_failure(key)
    raise refusal(...)

try:
    final_text = extract_complete_final_text(response)
except representation_problem:
    record_failure(key)
    raise CongineUnsupportedRepresentationError(...)

if state contains streamed text:
    if response is None:
        refuse

    streamed_text = join(state.parts)

    if streamed_text != final_text:
        refuse

    completion = streamed_text
else:
    completion = final_text

result = validate_contract_usecase.execute(...)

record_result(key, result)

return result
```

The crucial order is:

```text
representation truth
BEFORE
policy evaluation
```

---

# 34. Unit test matrix

| ID | Scenario | Expected result | `execute()` calls |
|---|---|---|---:|
| U01 | One plain final text generation | PASS path | 1 |
| U02 | One plain chat message with string content | PASS path | 1 |
| U03 | Complete text stream + matching final response | PASS path | 1 |
| U04 | Explicit `Generation(text="")` | Evaluate explicit empty text | 1 |
| U05 | Custom payload key | Correct key used | 1 |
| U06 | Multiple valid concurrent runs | Isolated | one/run |
| U07 | Exactly buffer limit | Supported | 1 |
| U08 | Buffer limit + 1 char | refusal | 0 |
| U09 | Overflow token would partly fit | no clipping; refusal | 0 |
| U10 | Non-string stream token | sticky refusal | 0 |
| U11 | Text → unsupported → text | remains refused | 0 |
| U12 | Missing run ID | refusal | 0 |
| U13 | Unhashable run ID | refusal | 0 |
| U14 | No generations | refusal | 0 |
| U15 | Multiple generation groups | refusal | 0 |
| U16 | Multiple candidates | refusal | 0 |
| U17 | Structured/list message content | refusal | 0 |
| U18 | Image-only content | refusal | 0 |
| U19 | Tool calls present | refusal | 0 |
| U20 | Function/action data in additional kwargs | refusal | 0 |
| U21 | String stream + final tool call | refusal | 0 |
| U22 | Stream/final text mismatch | refusal | 0 |
| U23 | Stream + `response=None` | refusal | 0 |
| U24 | Observable `finish_reason=length` | refusal | 0 |
| U25 | Observable max-token truncation | refusal | 0 |
| U26 | Malformed `generations` property raises | representation refusal | 0 |
| U27 | Text field and message content disagree | refusal | 0 |
| U28 | Refusal clears active text state | no retained payload | 0 |
| U29 | Refusal leaves `result_for()` empty | `None` | 0 |
| U30 | Existing `CongineContractNotFoundError` | re-raised | 1 attempted |
| U31 | Existing strict `CongineValidationError` | re-raised | 1 |
| U32 | Logger failure during refusal | original refusal survives | 0 |
| U33 | Closed container before token | lifecycle error, no mutation | 0 |
| U34 | Closed container before end | lifecycle error, state unchanged per current lifecycle rule | 0 |
| U35 | LLM error after partial stream | state discarded | 0 |
| U36 | Raw unsupported payload contains secret marker | secret absent from logs | 0 |

---

# 35. Real CallbackManager integration test

Create:

```text
tests/integration/test_langchain_callback_manager.py
```

This must use actual:

```python
langchain_core.callbacks.manager.CallbackManager
```

not a fake callback manager.

Basic pattern:

```python
manager = CallbackManager([handler])

run_managers = manager.on_llm_start(
    {"name": "p2-03a1-test"},
    ["prompt"],
)

run = run_managers[0]
```

Then invoke the callback through `run`.

### Integration matrix

| ID | Scenario | Required witness |
|---|---|---|
| LC01 | Supported text final response | callback manager completes; use case called once |
| LC02 | `CongineUnsupportedRepresentationError` from handler | exception escapes CallbackManager |
| LC03 | Strict `CongineValidationError` | exception escapes CallbackManager |
| LC04 | Unsupported streamed observation | manager propagates refusal |
| LC05 | Handler property | `handler.raise_error is True` |

LC02 and LC03 are the closure-critical tests.

Without them, direct handler behavior is not enough.

---

# 36. Real-container integration tests

Keep/modify:

```text
tests/integration/test_end_to_end.py
```

Required cases:

### Complete supported stream

Use a real `ServiceContainer`.

```text
tokens
+
matching final LLMResult
        ↓
one validation event
        ↓
PASS
```

### Unsupported representation

Use real container and fake event bus.

Example:

```text
multiple generations
        ↓
representation refusal
        ↓
zero validation calls
        ↓
zero validation telemetry events
```

This proves refusal happened before the use case.

---

# 37. Example update

The existing manual stream example must change from:

```python
handler.on_llm_end(run_id=session_id)
```

to something conceptually equivalent to:

```python
final_text = "Hello your claim is valid."

response = LLMResult(
    generations=[
        [
            Generation(text=final_text),
        ]
    ]
)

handler.on_llm_end(
    response=response,
    run_id=session_id,
)
```

The exact LangChain imports must match the pinned `0.3.x` API.

Do not upgrade LangChain to make the example easier.

---

# 38. Must-not-change boundary: dependency versions

P2-03a1 must **not modify**:

```toml
langchain = ["langchain-core>=0.3,<0.4"]
```

No:

```text
0.3 → 1.x
```

in this milestone.

No lockfile churn except if an unrelated reproducibility reason absolutely requires it—and if that happens, stop and split it into a separate change.

P2-03a will own LangChain dependency remediation/migration.

---

# 39. Must-not-change boundary: policy engine

Do not modify:

```text
domain/
RuleEngine
LocalValidator
CompositeValidator
schema vocabulary
contract admission
```

P2-03a1 does not add new policy rules.

The policy engine is not the root cause.

---

# 40. Must-not-change boundary: use case

Do not change:

```text
ValidateContractUseCase
```

to understand LangChain.

LangChain remains an L5 concern.

Forbidden:

```text
L3 knows what AIMessage is
L3 knows what Generation is
L3 knows what tool_calls are
```

The use case receives only the supported normalized payload after L5 has established representation completeness.

---

# 41. Must-not-change boundary: result model

Do not add a fake result such as:

```python
ValidationResult(
    status="fail",
    reason="unsupported_langchain_output",
)
```

P2-03a1 representation refusal occurs **before policy evaluation**.

Therefore:

```text
no ValidationResult exists
```

Do not modify:

```text
ValidationResult
DegradedReason
EvaluationStage
```

for this milestone.

---

# 42. Must-not-change boundary: fail mode

Do not change:

```text
STRICT
DEGRADE
```

semantics.

Representation completeness is a prerequisite to evaluation.

It is not something `DEGRADE` is permitted to turn into approval.

In other words:

```text
unsupported representation
```

must not become:

```text
degraded but allowed
```

inside the LangChain adapter.

---

# 43. Must-not-change boundary: configuration

Do not add:

```text
CONGINE_LANGCHAIN_ALLOW_MULTIMODAL
CONGINE_LANGCHAIN_IGNORE_TOOLS
CONGINE_ALLOW_TRUNCATED_STREAM
```

or similar switches.

There should be no config option that weakens representation completeness.

Keep:

```text
CONGINE_MAX_STREAM_BUFFER_CHARS
```

with its existing meaning as a resource bound.

Only change overflow behavior from:

```text
clip
```

to:

```text
refuse
```

---

# 44. Must-not-change boundary: no multimodal support

P2-03a1 must not implement:

```text
image normalization
content-block flattening
tool-call policy
function-call policy
structured subject governance
```

Those require the future Governed Subject model.

For now:

```text
unsupported → refuse
```

is the correct behavior.

---

# 45. Must-not-change boundary: no provider-specific logic

Do not add branches such as:

```python
if provider == "openai":
...
elif provider == "anthropic":
...
elif provider == "gemini":
...
```

P2-03a1 defines truth at the LangChain adapter boundary.

Provider expansion belongs later.

---

# 46. Must-not-change boundary: architecture

The current dependency matrix remains:

```text
L0 → L0
L1 → L0,L1
L2 → L0,L1,L2
L3 → L0,L1,L2,L3
L4 → L0,L1,L4
L5 → L0,L1,L2,L3,L4,L5
```

No exemptions.

No `TYPE_CHECKING` exemptions.

No new architecture allowlist.

The LangChain adapter remains L5.

The new exception remains L0.

---

# 47. Must-not-change boundary: optional dependency

This must remain true:

```python
import congine_core
```

does not require `langchain-core`.

Do not break the existing lazy adapter import.

`CongineCallbackHandler` must remain lazily reachable through:

```python
from congine_core.adapters import CongineCallbackHandler
```

without turning LangChain into a mandatory core dependency.

---

# 48. Must-not-change boundary: no raw logging

No raw host/model content may enter:

```text
StructuredLogger
exceptions
telemetry
completion report
test failure snapshots committed to repo
```

Tests should use obvious secret sentinel strings to verify this.

---

# 49. Must-not-change boundary: no silent extraction fallback

Forbidden:

```python
return ""
```

for unsupported shapes.

Forbidden:

```python
str(content)
```

Forbidden:

```python
content[0]["text"]
```

without accounting for remaining blocks.

Forbidden:

```python
generation[0][0]
```

while ignoring the rest.

Forbidden:

```python
first available text wins
```

---

# 50. Must-not-change boundary: concurrency

Existing guarantees for concurrent run isolation must remain.

No state from:

```text
run A
```

may enter:

```text
run B
```

and one run becoming refused must not mutate another active run.

---

# 51. Verification commands

First, targeted P2-03a1:

```bash
uv run --package congine-sdk \
  --extra langchain \
  --extra stats \
  --extra dev \
  pytest \
  libs/congine-sdk/tests/unit/test_langchain_handler.py \
  libs/congine-sdk/tests/integration/test_langchain_callback_manager.py \
  libs/congine-sdk/tests/integration/test_end_to_end.py \
  -q
```

Then existing project gates:

```bash
npm exec nx -- run congine-sdk:lint --skipNxCache
```

```bash
npm exec nx -- run congine-sdk:typecheck --skipNxCache
```

```bash
npm exec nx -- run congine-sdk:architecture --skipNxCache
```

```bash
npm exec nx -- run congine-sdk:examples --skipNxCache
```

```bash
npm exec nx -- run congine-sdk:test --skipNxCache
```

Then:

```bash
npm exec nx -- run congine-sdk:coverage --skipNxCache
```

and:

```bash
npm exec nx -- run congine-sdk:evidence-trust --skipNxCache
```

Finally:

```bash
git diff --check
```

Do not state a final passing-test count in advance.

Record whatever the completed repository actually produces.

---

# 52. P2-03a1 closure criteria

The milestone closes only when all of the following are true:

```text
[ ] Complete plain final text can be evaluated.
[ ] Complete textual streaming can be evaluated.
[ ] Streaming requires a compatible final representation.
[ ] Multiple generations are refused.
[ ] Multiple generation groups are refused.
[ ] Structured/multimodal content is refused.
[ ] Tool/action side channels are refused.
[ ] Unsupported stream observations are sticky.
[ ] Local stream overflow refuses rather than clips.
[ ] Observable truncation refuses.
[ ] Stream/final mismatch refuses.
[ ] Missing final response after streaming refuses.
[ ] Explicit empty text is distinguished from absent/unrepresentable text.
[ ] Invalid run identity cannot alias state.
[ ] Representation refusal calls ValidateContractUseCase zero times.
[ ] Representation refusal creates no ValidationResult.
[ ] Representation refusal creates no validation telemetry event.
[ ] Raw unsupported content never enters logs.
[ ] Direct CongineBaseException behavior remains intact.
[ ] Representation refusal propagates through real CallbackManager.
[ ] Strict policy BLOCK propagates through real CallbackManager.
[ ] Concurrent runs remain isolated.
[ ] Lifecycle semantics remain intact.
[ ] Optional LangChain import remains lazy.
[ ] Architecture gate remains zero-exemption.
[ ] No dependency version changes.
[ ] No domain/use-case/result-model changes.
[ ] Existing P0/P1/P1.5 evidence remains green.
```

---

# 53. Desired post-P2-03a1 behavior

The whole milestone reduces to this:

```text
                  LANGCHAIN OUTPUT
                         │
                         ▼
              Representation Boundary
                         │
             ┌───────────┴────────────┐
             │                        │
             ▼                        ▼
     COMPLETE + SUPPORTED      INCOMPLETE / UNSUPPORTED
             │                        │
             │                        ▼
             │                      REFUSE
             │                        │
             │                 execute() = 0
             │                        │
             │                 exception reaches
             │                       host
             ▼
    ValidateContractUseCase
             │
             ▼
      deterministic policy
             │
       ┌─────┴─────┐
       ▼           ▼
      PASS        FAIL
       │           │
     ALLOW       BLOCK
```

The most important sentence for the implementation review should be:

> **P2-03a1 does not make CONGINE understand more kinds of agent output. It makes CONGINE stop claiming governance over output it does not fully understand.**

That is the right hardening boundary before we touch **P2-03a / the LangChain dependency-security migration**.
