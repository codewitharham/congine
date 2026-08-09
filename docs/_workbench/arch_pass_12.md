## 13. Contract semantics — safety-critical

**Why this section exists.** Under the default configuration (`semantic_validation_enabled=False`)
the only thing evaluating a contract is `LocalValidator` running six rules. Any schema keyword those
rules do not read is **silently ignored**: the contract reports conformance while enforcing nothing.
A user who writes `{"summary": {"type": "string", "minLength": 10}}` and sees `status="pass"` has no
enforcement of `minLength` and no indication of that fact at validation time.

Every behaviour below was verified by executing it, not by reading it. Where a claim came out
differently than the source reads, the executed result is what is recorded.

### 13.1 The keywords the rule engine reads

`LocalValidator._extract_params` (`domain/validator.py:333-367`) is the complete answer. It consults
exactly three top-level keys and five per-property keys.

**Top-level (3):**

| Keyword | Read by | Line |
|---|---|---|
| `properties` | TYPE_MATCH (whole map), ENUM_VALUES / RANGE_CHECK / REGEX_PATTERN (filtered views) | `:341` |
| `required` | FIELD_PRESENCE | `:343` |
| `null_forbidden` | NULL_GUARD — **a Congine extension, not JSON Schema** | `:360` |

**Per-property (5 distinct keys, 7 spellings):**

| Keyword | Read by | Line |
|---|---|---|
| `type` | TYPE_MATCH | `:131` |
| `enum` | ENUM_VALUES (selection at `:347-351`) | `:160` |
| `min` / `minimum` | RANGE_CHECK (selection at `:352-358`) | `:188-190` |
| `max` / `maximum` | RANGE_CHECK | `:191-193` |
| `pattern` | REGEX_PATTERN (selection at `:361-366`) | `:245` |

`domain/schema_vocabulary.py:23-32` mirrors exactly this set, and
`tests/unit/test_schema_vocabulary.py:119` (`test_vocabulary_matches_rule_engine`) is the drift
guard that keeps the mirror honest.

### 13.2 The keywords the rule engine silently ignores

Everything else. Because `find_unenforced_keywords` uses **allowlist** semantics (anything not
enforced and not metadata is reported), the ignored set is open-ended by construction — which is the
correct design, since JSON Schema keeps growing. The commonly-used members:

| Category | Keywords | Enforced only when |
|---|---|---|
| String constraints | `minLength`, `maxLength`, `format`, `contentEncoding`, `contentMediaType` | `CONGINE_SEMANTIC_VALIDATION=true` |
| Numeric constraints | `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` | same |
| Array constraints | `items`, `minItems`, `maxItems`, `uniqueItems`, `contains`, `prefixItems` | same |
| Object constraints | `additionalProperties`, `minProperties`, `maxProperties`, `patternProperties`, `propertyNames`, `dependentRequired` | same |
| Composition | `allOf`, `anyOf`, `oneOf`, `not`, `if`/`then`/`else` | same |
| Value constraints | `const` | same |
| References | `$ref`, `$defs`, `definitions` | same |
| Nested schemas | a property's own `properties` | same |

**`const` and `additionalProperties` deserve a specific callout.** `const` is the natural way to pin
a value and it does nothing. `additionalProperties: false` is the natural way to reject unexpected
fields and it does nothing — the rule engine has no concept of an unexpected field at all, so a
payload may carry arbitrary extra keys under any contract.

Keywords treated as **metadata and deliberately never warned about**
(`schema_vocabulary.py:37-50`): `description`, `title`, `default`, `examples`, `$comment`,
`deprecated`, `readOnly`, `writeOnly`, `$schema`, `$id`.

**The P0-2 mitigation, and its precise limits.** Since the working-tree change, priming a contract
whose schema contains an unenforced keyword emits one WARNING naming the `field.keyword` paths
(`sync_contracts_usecase.py:295-300`). Three limits matter:

1. It fires **only on the cache-prime path** (`_prime_cache` → `_warn_unenforced_keywords`,
   `:270`). A schema written directly with `schema_storage.put(...)` — which tests, embedders and
   any future non-repository loader do — is never scanned.
2. It is **non-recursive by design** (`schema_vocabulary.py:93-96`): a property carrying nested
   `properties` or `items` is reported once at that field rather than enumerated. The whole subtree
   is unenforced either way, so this is a noise decision, not a coverage gap.
3. It is **detection, not enforcement**. Validation behaviour is unchanged.

### 13.3 Per-rule behaviour, with edge cases

All results below are executed, not inferred.

#### Rule 1 — `FIELD_PRESENCE` (`:97-116`)

Reads `schema["required"]` (default `[]`). For each name, `_path_present(payload, name)` (`:59-72`).

| Edge case | Behaviour | Verified |
|---|---|---|
| **Dot-notation** `"a.b.c"` | **Supported.** Each segment must exist and every intermediate must be a mapping | `{"a":{"b":1}}` + `required:["a.b"]` ⇒ **pass** |
| Non-dict intermediate | absent ⇒ breach | `:69-70` |
| Key present with value `None` | **counts as present** — nullability is NULL_GUARD's concern | `:65` and `test_field_presence_none_value_counts_as_present` |
| `required` is a **string** rather than a list | iterates its **characters** — `required: "ab"` requires fields `"a"` and `"b"` | `{"a":1}` + `required:"ab"` ⇒ one breach on field `"b"` |
| `required` absent | no breaches | `:343` |

#### Rule 2 — `TYPE_MATCH` (`:118-146`)

Reads the whole `properties` map. Skips absent fields (`:129-130`) and `None` values (`:135-137`).

`_JSON_TYPE_MAP` (`:49-56`) recognises exactly six type names: `string`→`(str,)`,
`number`→`(int,float)`, `integer`→`(int,)`, `boolean`→`(bool,)`, `object`→`(dict,)`,
`array`→`(list,)`. Missing relative to JSON Schema: **`null`**.

| Edge case | Behaviour | Verified |
|---|---|---|
| **bool vs number** | `True` is **not** a `number` and **not** an `integer` (`:82-83`), despite `bool` subclassing `int` in Python | `test_type_match_bool_is_not_integer/_number` |
| **int vs boolean** | only a genuine `bool` satisfies `"boolean"` (`:85-86`); `1` does not | `test_type_match_all_json_types` |
| int for `number` | accepted | `test_type_match_int_satisfies_number` |
| float for `integer` | rejected | `test_type_match_float_not_integer` |
| **Unrecognised type string** (e.g. `"null"`, `"str"`) | `_JSON_TYPE_MAP.get` ⇒ `None` ⇒ **returns `True`, no breach** (`:77-80`) — "do not flag a breach we cannot evaluate" | `test_type_match_unknown_type_is_ignored` |
| **Union / list type** `["string","null"]` | **raises `TypeError`** — `dict.get` with an unhashable list. See §13.6 | executed: `TypeError: cannot use 'list' as a dict key` |
| Bare-string spec `{"a": "string"}` | supported — `spec` is used directly as the type name (`:131`) | `{"a":1}` + `{"a":"string"}` ⇒ **fail** |
| Falsy `type` (`""`, `None`, absent) | skipped (`:132-133`) | `:132` |
| **Dot-notation** | **not supported** — `field_name not in payload` is a flat lookup (`:129`) | `{"a":{"b":1}}` + `properties:{"a.b":{"type":"string"}}` ⇒ **pass** |

#### Rule 3 — `ENUM_VALUES` (`:148-169`)

Selected for properties whose spec is a dict containing `"enum"` (`:347-351`).

| Edge case | Behaviour | Verified |
|---|---|---|
| Field absent | skipped (`:158-159`) | `test_enum_values_absent_field_ok` |
| **Value is `None` and present** | **breach** — ENUM_VALUES does *not* skip `None` the way TYPE_MATCH does | `{"a":None}` + `enum:["x"]` ⇒ **fail**. Genuine inconsistency across rules |
| Membership test | `payload[field] not in allowed` — Python `in`, so `1 == True` and `1.0 == 1` match | `:161` |
| `enum` present but not a list | `in` against whatever it is; a string enum does substring matching | `:160` |
| Bare non-dict spec | `spec` used directly as the allowed collection (`:160`) | `:160` |
| **Dot-notation** | not supported | flat lookup at `:158` |

#### Rule 4 — `RANGE_CHECK` (`:171-210`)

Selected for dict specs containing any of `min`, `max`, `minimum`, `maximum` (`:352-358`).

| Edge case | Behaviour | Verified |
|---|---|---|
| Non-numeric value | skipped — TYPE_MATCH's concern (`:185-187`) | `test_range_check_ignores_non_numeric_and_bool` |
| **bool value** | explicitly skipped (`isinstance(value, bool)` at `:185`) | `{"a":True}` + `min:0,max:0` ⇒ **pass** |
| `min` / `minimum` aliases | `spec.get("min", spec.get("minimum"))` (`:188-190`) — `min` wins | `test_range_check_minimum_maximum_aliases` |
| **Explicit `min: None` alongside `minimum: 10`** | `spec.get("min", …)` finds the key and returns `None`, so the `minimum` fallback is **never consulted** and no bound is applied | `{"a":5}` + `{"min":None,"minimum":10}` ⇒ **pass** (should fail) |
| `min: 0` | works — the check is `is not None`, not truthiness (`:194`) | `{"a":-5}` + `min:0` ⇒ **fail** |
| **Both bounds violated** | `elif` at `:202` ⇒ **only the min breach is reported** | `{"a":100}` + `{"min":200,"max":50}` ⇒ one breach, `"below minimum 200"` |
| Comparison | plain `<` / `>` — inclusive bounds; no `exclusiveMinimum` support | `:194`, `:202` |
| **Dot-notation** | not supported | flat lookup at `:182` |

#### Rule 5 — `NULL_GUARD` (`:212-227`)

Reads `schema["null_forbidden"]` — a **Congine-specific extension with no JSON Schema equivalent**.

| Edge case | Behaviour | Verified |
|---|---|---|
| Field absent | no breach — only `present and is None` breaches (`:219`) | `test_null_guard_passes_non_none_and_absent` |
| Field present, non-`None` | no breach | same |
| **Dot-notation** | **not supported** | `{"a":{"b":None}}` + `null_forbidden:["a.b"]` ⇒ **pass** |
| `null_forbidden` absent | no breaches | `:360` |

Because this keyword is not JSON Schema, `JsonSchemaSemanticValidator` ignores it entirely — it is
one of the few constraints enforced by the rule engine and **not** by the semantic validator.
Symmetrically, `find_unenforced_keywords` explicitly allowlists it (`schema_vocabulary.py:24`) so it
is never warned about.

#### Rule 6 — `REGEX_PATTERN` (`:229-290`)

Selected for dict specs containing `"pattern"` (`:361-366`).

| Edge case | Behaviour | Verified |
|---|---|---|
| Non-string value | skipped — TYPE_MATCH's concern (`:242-244`) | `test_regex_pattern_skips_non_string` |
| **Anchoring** | `fullmatch` (`:271`) — **the entire value must match**. A pattern of `abc` does **not** match `"xabcx"` | executed: `{"a":"xabcx"}` + `pattern:"abc"` ⇒ **fail**. This diverges from JSON Schema, where `pattern` is an unanchored *search* |
| **Pattern longer than 1000 chars** | breach `"Pattern for '<f>' exceeds the safe length budget"`, no compilation (`:252-260`) — fail-closed | `MAX_PATTERN_LENGTH` |
| **Value longer than 50 000 chars** | breach `"Value for '<f>' is too long to match safely"`, no matching (`:261-269`) — fail-closed | `MAX_REGEX_VALUE_LENGTH` |
| **Invalid pattern** | `re2.error` ⇒ breach `"Invalid regex pattern for '<f>'"` (`:272-280`) — fail-closed, does **not** degrade | executed. `re2` also writes its own parse error to stderr, outside the structured logger |
| Empty/falsy pattern | skipped (`:246-247`) | `:246` |
| Engine | `google-re2` — linear-time, no catastrophic backtracking. A **required core dependency** (FIX-02), never optional | `:14`, `:38` |
| Compilation caching | `functools.lru_cache(maxsize=512)` keyed on the pattern string, process-wide (`:41-44`) | `:41` |
| **Syntax differences** | RE2 does not support backreferences or lookaround. Such a pattern raises `re2.error` ⇒ an "Invalid regex pattern" breach, i.e. a *contract* failure rather than a schema-authoring error | `:272` |
| **Dot-notation** | not supported | flat lookup at `:239` |

### 13.4 Dot-notation: exactly one rule supports it

This is the single easiest way to write a contract that does nothing.

| Rule | Dot-notation | Mechanism |
|---|---|---|
| `FIELD_PRESENCE` | **YES** | `_path_present` walks segments (`:59-72`) |
| `TYPE_MATCH` | no | `field_name not in payload` (`:129`) |
| `ENUM_VALUES` | no | `field_name not in payload` (`:158`) |
| `RANGE_CHECK` | no | `field_name not in payload` (`:182`) |
| `NULL_GUARD` | no | `field_name in payload` (`:219`) |
| `REGEX_PATTERN` | no | `field_name not in payload` (`:239`) |

A contract reading `{"required": ["user.email"], "properties": {"user.email": {"type": "string",
"pattern": "^.+@.+$"}}}` enforces **presence only**. The type and pattern constraints are evaluated
against a top-level key literally named `"user.email"`, which does not exist, so both rules skip
silently. Nothing warns: `find_unenforced_keywords` inspects keyword *names*, not field-name shapes,
so `user.email.type` and `user.email.pattern` are both in the enforced set and are not reported.
Recorded as debt D16 in §16.

### 13.5 The security caps, restated

| Cap | Value | Constant | Applied at | Behaviour on breach |
|---|---|---|---|---|
| Pattern length | 1 000 chars | `MAX_PATTERN_LENGTH` | `validator.py:252`; also pre-checked by the semantic validator `jsonschema_validator.py:158` | fail-closed breach |
| Regex value length | 50 000 chars | `MAX_REGEX_VALUE_LENGTH` | `validator.py:261` | fail-closed breach |
| Payload size | 1 MiB | `DEFAULT_MAX_PAYLOAD_BYTES` | `validate_contract_usecase.py:130` | `INPUT_BOUNDS` breach |
| Schema size | 1 MiB | `DEFAULT_MAX_SCHEMA_BYTES` | `:148` | `INPUT_BOUNDS` breach |
| Semantic breaches | 100 | `DEFAULT_SEMANTIC_MAX_BREACHES` | `jsonschema_validator.py:125` | truncation marker |
| Contract files | 1 000 | `DEFAULT_MAX_CONTRACT_FILES` | `file_contract_repository.py:71`, `:100` | scan stops |
| Stream buffer | 500 000 chars | `DEFAULT_MAX_STREAM_BUFFER_CHARS` | `langchain_handler.py:77-82` | tokens silently clipped |
| HTTP response | 10 MiB | `DEFAULT_MAX_HTTP_RESPONSE_BYTES` | `http_contract_repository.py:121` | `CongineSyncError` |
| Reported unenforced paths | 20 | `_MAX_REPORTED` | `schema_vocabulary.py:141-143` | `"... (+N more)"` |
| Warned-contract de-dup set | 4 096 | `_MAX_WARNED_CONTRACTS` | `sync_contracts_usecase.py:292` | set cleared wholesale |

Every one of these is fail-closed except the stream-buffer clip (silently truncates) and the
`_MAX_WARNED_CONTRACTS` reset (re-warns after a clear).

### 13.6 The two malformed-schema shapes that degrade instead of failing

Both were verified end-to-end through `ValidateContractUseCase`, and both are more dangerous than a
breach because the caller sees `is_pass() == False` with **zero breaches** and, in `degrade` mode,
only a WARNING.

**Shape 1 — a union / list `type` declaration.**

```json
{"properties": {"a": {"type": ["string", "null"]}}}
```

This is legal JSON Schema and the idiomatic way to express a nullable field. `_type_matches` does
`_JSON_TYPE_MAP.get(json_type)` with an unhashable `list`, raising
`TypeError: cannot use 'list' as a dict key`. That propagates out of the rule, out of the validator,
out of the pool future, and is caught by `execute`'s generic handler (`:79-82`).

Observed: `status="fail"`, `degraded=True`, `degraded_reason="internal_error"`, `breaches=()`, ERROR
log `"Validation error" error_type=TypeError`. **Every validation against that contract degrades,
permanently, for as long as the schema is cached.** Under `fail_mode=silent` there is not even a
log line at the use-case level.

P0-2 mitigates the *discovery* problem: `find_unenforced_keywords` reports `a.type` for a non-string
type value (`schema_vocabulary.py:99-101`, `_type_is_enforceable` at `:77-79`), and
`test_unrecognised_and_union_types_flagged` pins it. So a contract loaded through the repository now
warns at load. A schema injected via `schema_storage.put()` still does not.

**Shape 2 — a non-dict schema.** A cached value that is not a mapping (e.g. a string) makes
`_extract_params` call `schema.get(...)` ⇒ `AttributeError` ⇒ the same `internal_error` degrade.
Verified. Neither `_prime_cache` nor `LFUCache.put` type-checks the schema, so any repository that
yields `{"id": "x", "schema": "oops"}` produces this.

### 13.7 What a contract author needs to know, in one place

1. Only **`required`, `properties`, `null_forbidden`** at the top level and
   **`type`, `enum`, `min`/`minimum`, `max`/`maximum`, `pattern`** per property are enforced by
   default. Everything else — including `minLength`, `format`, `const`, `additionalProperties`,
   `items`, `allOf` — is ignored unless `CONGINE_SEMANTIC_VALIDATION=true`.
2. **`pattern` is a full match**, not a search. Patterns written for JSON Schema will over-reject.
3. **Dot-notation works only in `required`.** Nested constraints are silently unenforced.
4. **A union `type` (`["string","null"]`) breaks the contract entirely** — every validation degrades.
   Use a single type name and `null_forbidden`.
5. **Booleans are never numbers and never integers**, and `1` is never a boolean.
6. **`enum` treats a present `None` as a violation**; `type` does not. If a field is nullable and
   enumerated, `None` will breach.
7. **An unrecognised `type` name is not an error** — it disables type checking for that field.
8. When only `min` and `max` are both violated, **only the `min` breach is reported**.
9. The contract cannot reject unexpected fields. There is no `additionalProperties` enforcement.
10. Since P0-2, loading a contract with unenforced keywords logs one WARNING naming them. **Watch
    for it at boot.** It is your only signal that part of your contract is decorative.
