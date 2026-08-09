## 12. Configuration surface

`CongineConfig` (`config.py:60-363`) is a `frozen=True` dataclass with **exactly 46 fields**, every
one of which maps 1:1 to a `CONGINE_*` environment variable read by `from_env()` (`:151-255`). Field
count and env-var count were both enumerated programmatically and agree at 46.

The prior documents say "~45 fields" (`00_SYSTEM_MAP.md:260`, `01_FILE_INVENTORY.md:21`). The exact
current number is 46.

### 12.1 The complete field table

`Where it lands` gives the concrete and line the value actually reaches. `Validation` describes what
`from_env()` does with a bad value.

#### Control plane (5)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 1 | `base_url` | `str` | `"http://localhost:8080"` | `CONGINE_BASE_URL` | HTTPS policy in `validate()` `:274-283`; parsed by `is_local_base_url()` `:285-295` | `http_contract_repository.py:112` (fetch URL), `queue_event_bus.py:234` (telemetry URL), `_scope_key` `:56` (snapshot path), cleartext warning `dependency_injection.py:216` | the control-plane host, the snapshot scope, and whether credential/HTTPS/redaction policy applies |
| 2 | `api_key` | `Optional[str]` | `None` | `CONGINE_API_KEY` | required when non-local `:261-273` | `X-API-Key` header in both repository `:108` and bus `:236`; `_scope_key` excludes it deliberately | authentication |
| 3 | `project_id` | `Optional[str]` | `None` | `CONGINE_PROJECT_ID` | required when non-local | `X-Project-ID` header `:109`, `:237`; `_scope_key` `:56` | tenancy scoping on the wire and on disk |
| 4 | `tenant_id` | `Optional[str]` | `None` | `CONGINE_TENANT_ID` | required when non-local | `X-Tenant-ID` header `:110`, `:238`; `_scope_key` `:56` | tenancy scoping on the wire and on disk |
| 5 | `region` | `Region` | `Region.US` | `CONGINE_REGION` | `ValueError` → `CongineConfigurationError` `:154-159` | **nowhere** | **nothing — see §12.4** |

#### Validation (2)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 6 | `validation_timeout_ms` | `int` | `100` | `CONGINE_TIMEOUT_MS` | `_env_int` raises on non-int `:330-340` | `ValidateContractUseCase(timeout_ms=…)` `dependency_injection.py:307` | the hard per-validation deadline |
| 7 | `fail_mode` | `FailMode` | `DEGRADE` | `CONGINE_FAIL_MODE` | `ValueError` → `CongineConfigurationError` `:160-165` | `ValidateContractUseCase(fail_mode=…)` `:308` | raise / warn / silence on breach |

#### Cache (3)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 8 | `cache_capacity` | `int` | `500` | `CONGINE_CACHE_CAPACITY` | `_env_int`; `LFUCache` rejects negative `:48-49` | `LFUCache(capacity=…)` `:230` | max cached schemas before LFU eviction. **`0` disables caching entirely** (`lfu_cache.py:110-111` makes `put` a no-op) |
| 9 | `cache_ttl_seconds` | `int` | `300` | `CONGINE_CACHE_TTL` | `_env_int` | `LFUCache(ttl_seconds=…)` `:231` **and** `SyncContractsUseCase(cache_ttl_seconds=…)` `:317` | per-entry TTL; the sync use case passes it explicitly on every `put` |
| 10 | `cache_sweep_interval_seconds` | `float` | `30.0` | `CONGINE_CACHE_SWEEP_INTERVAL_SECONDS` | `_env_float` `:350-360` | `LFUCache(sweep_interval=…)` `:232` | sweeper cadence; also bounds `stop()`'s join |

#### Background sync (2)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 11 | `sync_enabled` | `bool` | `False` | `CONGINE_SYNC_ENABLED` | `_env_bool` `:320-328` | read in `bootstrap()` `:356` and `bootstrap_async()` `:362` | whether `bootstrap()` starts the periodic sync daemon |
| 12 | `sync_interval_seconds` | `int` | `300` | `CONGINE_SYNC_INTERVAL` | `_env_int` | `BackgroundSyncWorker(interval_seconds=…)` `:331` | sync cadence; also bounds `stop()`'s join |

#### Semantic validation & drift (6)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 13 | `semantic_validation_enabled` | `bool` | `False` | `CONGINE_SEMANTIC_VALIDATION` | `_env_bool` | validator branch `:293`; `SyncContractsUseCase(semantic_validation_enabled=…)` `:320` | `LocalValidator` vs `CompositeValidator`, **and** whether the P0-2 unenforced-keyword warning fires |
| 14 | `semantic_max_breaches` | `int` | `100` | `CONGINE_SEMANTIC_MAX_BREACHES` | `_env_int` | `JsonSchemaSemanticValidator(max_breaches=…)` `:282` | cap on drained `iter_errors`; a `SEMANTIC_TRUNCATED` marker is appended when hit |
| 15 | `semantic_format_checking` | `bool` | `False` | `CONGINE_SEMANTIC_FORMAT_CHECKING` | `_env_bool` | `JsonSchemaSemanticValidator(format_checking=…)` `:283` | whether `format` assertions are enforced |
| 16 | `drift_threshold` | `float` | `0.1` | `CONGINE_DRIFT_THRESHOLD` | `_env_float` | `KSDriftEngine(threshold=…)` `:287` | the **D-statistic** above which drift is flagged (not the p-value — see §11.3) |
| 17 | `drift_sample_limit` | `int` | `500` | `CONGINE_DRIFT_SAMPLE_LIMIT` | `_env_int`; `KSDriftEngine` rejects ≤ 0 `:62-63` | `KSDriftEngine(max_samples=…)` `:288` | reference-window `deque` maxlen |
| 18 | `jsonschema_draft` | `str` | `"draft202012"` | `CONGINE_JSONSCHEMA_DRAFT` | **fail-closed at container construction** via `_resolve_draft` `jsonschema_validator.py:54-68` | `JsonSchemaSemanticValidator(jsonschema_draft=…)` `:284` | which JSON Schema dialect validates. 16 accepted spellings; anything else raises even when semantic validation is off |

#### Validation pool (2)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 19 | `validation_max_workers` | `int` | `10` | `CONGINE_VALIDATION_WORKERS` | `_env_int`; executor rejects ≤ 0 `:49-50` | `BoundedValidationExecutor(max_workers=…)` `:225` | pool size; half of `capacity` |
| 20 | `validation_max_pending` | `int` | `10` | `CONGINE_VALIDATION_PENDING` | `_env_int`; executor rejects < 0 `:51-52` | `BoundedValidationExecutor(max_pending=…)` `:226` | queue slack; `capacity = workers + pending` |

#### Contract source (3)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 21 | `contract_source` | `str` | `"http"` | `CONGINE_CONTRACT_SOURCE` | lower-cased `:201`; **any unrecognised value silently means HTTP** | repository branch `:252` | selects the file repository only in combination with `contracts_dir` |
| 22 | `contracts_dir` | `Optional[str]` | `None` | `CONGINE_CONTRACTS_DIR` | none | `FileContractRepository(contracts_dir=…)` `:254` | contract directory in the non-standalone file mode |
| 23 | `local_contracts_dir` | `Optional[str]` | `None` | `CONGINE_LOCAL_CONTRACTS_DIR` | none — **`""` is truthy for `is not None`** | `_standalone` `:243`, `FileContractRepository` `:247` | the standalone switch: file repo **and no sync worker at all** |

#### Telemetry (7)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 24 | `telemetry_enabled` | `bool` | `True` | `CONGINE_TELEMETRY_ENABLED` | `_env_bool` | bus branch `:262` | `QueueEventBus` vs `NoOpEventBus` — thread and socket, or neither |
| 25 | `telemetry_queue_size` | `int` | `10_000` | `CONGINE_TELEMETRY_QUEUE_SIZE` | `_env_int` | `QueueEventBus(max_queue_size=…)` `:270` | buffered events before `publish` starts dropping |
| 26 | `telemetry_batch_size` | `int` | `100` | `CONGINE_TELEMETRY_BATCH_SIZE` | `_env_int` | `QueueEventBus(batch_size=…)` `:271` | events per POST |
| 27 | `telemetry_max_retries` | `int` | `4` | `CONGINE_TELEMETRY_MAX_RETRIES` | `_env_int` | `QueueEventBus(max_retries=…)` `:272` | attempts before a batch is dropped and the breaker records a failure |
| 28 | `telemetry_backoff_base` | `float` | `0.5` | `CONGINE_TELEMETRY_BACKOFF_BASE` | `_env_float` | `QueueEventBus(backoff_base=…)` `:273` | first retry delay; doubles each attempt |
| 29 | `telemetry_backoff_max` | `float` | `8.0` | `CONGINE_TELEMETRY_BACKOFF_MAX` | `_env_float` | `QueueEventBus(backoff_max=…)` `:274` | backoff ceiling |
| 30 | `control_plane_http_timeout_seconds` | `float` | `10.0` | `CONGINE_CONTROL_PLANE_HTTP_TIMEOUT` | `_env_float` | `httpx.Client` factory `:276` **and** `AsyncClient` `http_contract_repository.py:117` | HTTP timeout on both control-plane paths; the worst-case boot stall when the breaker is CLOSED |

#### Snapshot / security / observability (7)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 31 | `snapshot_dir` | `Optional[str]` | `None` → `_default_snapshot_dir()` | `CONGINE_SNAPSHOT_DIR` | none | `http_contract_repository.py:71` | snapshot location; default is a per-user app dir, never `/tmp` |
| 32 | `snapshot_lock_timeout_seconds` | `float` | `10.0` | `CONGINE_SNAPSHOT_LOCK_TIMEOUT` | `_env_float` | `portalocker.Lock(timeout=…)` `http_contract_repository.py:231` | how long a writer waits before skipping its best-effort snapshot write |
| 33 | `require_https` | `bool` | `True` | `CONGINE_REQUIRE_HTTPS` | `_env_bool` | `self.require_https` in `validate()` `:275` | whether the HTTPS policy is enforced at all |
| 34 | `allow_cleartext` | `bool` | `False` | `CONGINE_ALLOW_CLEARTEXT` | `_env_bool` | `self.allow_cleartext` in `validate()` `:276`; drives the boot warning `dependency_injection.py:216-223` | the explicit escape hatch for a non-HTTPS control plane |
| 35 | `log_level` | `str` | `"INFO"` | `CONGINE_LOG_LEVEL` | upper-cased `:225`; **unknown values silently fall back to INFO** `logger.py:63` | `StructuredLogger(level=…)` `:213` | severity threshold |
| 36 | `log_safe_fields` | `Optional[FrozenSet[str]]` | `None` | `CONGINE_LOG_SAFE_FIELDS` | comma-split, blanks dropped `:342-348` | via `effective_log_safe_fields()` → `StructuredLogger(log_safe_fields=…)` `:214` | explicit allowlist; overrides auto-redaction |
| 37 | `log_redaction_enabled` | `bool` | `True` | `CONGINE_LOG_REDACTION` | `_env_bool` | `self.log_redaction_enabled` in `effective_log_safe_fields()` `:301` | whether non-local deployments get the 12-key auto-allowlist |

#### Circuit breaker (2)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 38 | `breaker_failure_threshold` | `int` | `5` | `CONGINE_BREAKER_FAILURE_THRESHOLD` | `_env_int`; breaker rejects ≤ 0 `:52-53` | `CircuitBreaker(failure_threshold=…)` `:236` | consecutive failures before OPEN |
| 39 | `breaker_cooldown_seconds` | `float` | `30.0` | `CONGINE_BREAKER_COOLDOWN_SECONDS` | `_env_float`; breaker rejects < 0 `:54-55` | `CircuitBreaker(cooldown_seconds=…)` `:237` | OPEN duration before a HALF_OPEN probe |

#### Deployment (1)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 40 | `deployment_mode` | `DeploymentMode` | `SINGLE_TENANT` | `CONGINE_DEPLOYMENT_MODE` | `ValueError` → `CongineConfigurationError` `:166-174` | `get_default()` guard `:90`; forced to `MULTI_TENANT` by `for_tenant()` `:141`; `CongineCallbackHandler` guard `:46` | whether the process-wide singleton is usable |

#### Input bounds (5)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 41 | `max_payload_bytes` | `int` | `1_048_576` | `CONGINE_MAX_PAYLOAD_BYTES` | `_env_int` | `ValidateContractUseCase(max_payload_bytes=…)` `:309` | payload size ceiling (measured as JSON-encoded characters — §12.3) |
| 42 | `max_schema_bytes` | `int` | `1_048_576` | `CONGINE_MAX_SCHEMA_BYTES` | `_env_int` | `ValidateContractUseCase(max_schema_bytes=…)` `:310` **and** `FileContractRepository(max_file_bytes=…)` `:250`, `:257` | schema size ceiling **and** per-contract-file read cap — one knob, two meanings |
| 43 | `max_contract_files` | `int` | `1000` | `CONGINE_MAX_CONTRACT_FILES` | `_env_int` | `FileContractRepository(max_contract_files=…)` `:249`, `:256` | directory-scan cap |
| 44 | `max_stream_buffer_chars` | `int` | `500_000` | `CONGINE_MAX_STREAM_BUFFER_CHARS` | `_env_int` | `CongineCallbackHandler._max_buffer_chars` `langchain_handler.py:60-64` | LangChain token-buffer cap; excess is silently clipped |
| 45 | `max_http_response_bytes` | `int` | `10_485_760` | `CONGINE_MAX_HTTP_RESPONSE_BYTES` | `_env_int` | `http_contract_repository.py:114,121` | control-plane response ceiling, checked before parsing |

#### Container lifecycle (1)

| # | Field | Type | Default | Env var | Validation | Where it lands | What it changes |
|---|---|---|---|---|---|---|---|
| 46 | `start_background_services` | `bool` | `True` | `CONGINE_START_BACKGROUND_SERVICES` | `_env_bool` | `BoundedValidationExecutor(register_atexit=…)` `:227`, `LFUCache(start_sweeper=…)` `:233`, `QueueEventBus(start_worker=…)` `:279` | suppresses **three** things at once: the executor's atexit hook, the sweeper thread + its atexit hook, and the drain thread + its atexit flush |

### 12.2 Policy methods on the config object

`CongineConfig` is not a passive bag; it enforces three policies.

- **`validate()`** (`:257-283`) — called at the end of `from_env()` (`:254`), so environment-derived
  configs are always validated but directly-constructed ones are not. Returns immediately for a
  local base URL (`:259-260`). Otherwise requires all of `api_key`, `project_id`, `tenant_id`
  (`:261-273`), then enforces HTTPS unless `allow_cleartext` (`:274-283`).
- **`is_local_base_url()`** (`:285-295`) — parses the URL and compares the **hostname** against
  `{"localhost","127.0.0.1","::1","0.0.0.0"}` (`:31`). This is FIX-01: substring matching would
  accept `localhost.evil.com` and `notlocalhost`; hostname parsing rejects both. An unparseable or
  empty hostname returns `False` (fail-secure — policy applies).
- **`effective_log_safe_fields()`** (`:297-318`) — precedence: an explicit `log_safe_fields` wins;
  otherwise redaction disabled *or* a local URL ⇒ `None` (no redaction); otherwise a 12-key
  allowlist (`contract_id`, `contract_version`, `status`, `duration_ms`, `rule`, `field`,
  `error_type`, `breaches`, `count`, `attempt`, `timeout_ms`, `degraded`). This is FIX-08: a
  production (non-local) deployment gets PII-safe logging **by default**, without configuration.

### 12.3 Env-parsing helpers, and their edge behaviour

| Helper | Line | Behaviour on a bad value |
|---|---|---|
| `_env_bool` | `:320-328` | `{"0","false","no","off"}` ⇒ `False`; `{"1","true","yes","on"}` ⇒ `True`; **anything else ⇒ `False`**, silently. So `CONGINE_TELEMETRY_ENABLED=TRUE!` disables telemetry with no error |
| `_env_int` | `:330-340` | raises `CongineConfigurationError` naming the variable |
| `_env_float` | `:350-360` | raises `CongineConfigurationError` naming the variable |
| `_env_frozenset` | `:342-348` | comma-split, whitespace-stripped, blanks dropped; `""` ⇒ an **empty frozenset**, which means "redact everything" — different from unset (`None` = no redaction) |

Note the asymmetry: numeric fields fail loudly, boolean fields fail silently toward `False`. For
`require_https` that direction is safe (a typo cannot disable HTTPS enforcement, because
`allow_cleartext` must be explicitly *true*); for `telemetry_enabled` and
`start_background_services` a typo silently disables a subsystem.

**On the size guards.** `_check_payload_size`/`_check_schema_size` measure
`len(json.dumps(value, default=str))`. Because `json.dumps` defaults to `ensure_ascii=True`, its
output is pure ASCII, so `len(str)` is exactly the byte length of that encoding. Relative to a
compact UTF-8 encoding of the same data the measure **over**-counts (measured: a payload whose
compact UTF-8 form is 29 bytes is measured as 69). The guard is therefore *conservative* — it
rejects earlier than a true byte count would, never later. The field name `max_payload_bytes` is
still inaccurate (it is a JSON-encoded-character count, not a wire-size count), but the prior
audit's claim that it "undercounts vs the byte-named budget" is **inverted**. See §16 debt D6.

### 12.4 Dead configurables

**One field is defined, validated, documented, and never read: `region` (field 5).**

- Declared `config.py:73`.
- Parsed and validated in `from_env()` `:154-159` — an invalid value raises
  `CongineConfigurationError`, so it is not inert at load.
- Assigned `:181`.
- Documented in `README.md` as "`us` | `eu` | `apac`".
- **Zero reads.** `grep -rn "region" src/congine_core/` returns exactly four hits, all inside
  `config.py` itself (the enum definition, the field, the `from_env` parse, the constructor
  argument). No concrete, no use case, no adapter consults it. It does not affect `base_url`, does
  not select an endpoint, and does not appear in any header.

A user setting `CONGINE_REGION=eu` in the belief that it routes to a Frankfurt/GDPR endpoint gets no
such behaviour and no warning. The enum's own comments (`config.py:40-42`, naming Virginia,
Frankfurt (GDPR) and Singapore) actively encourage that belief. Given the compliance connotation,
this is the most consequential dead knob the system could have. Recorded as debt D1 in §16.

No other field is dead. The four that look suspicious are all genuinely consumed via `self.` inside
`config.py`'s own policy methods rather than via `config.<field>` at a call site: `require_https`
and `allow_cleartext` in `validate()`, `log_safe_fields` and `log_redaction_enabled` in
`effective_log_safe_fields()`.

### 12.5 Wired but undocumented

`README.md`'s configuration reference table — described in `.claude/CLAUDE.md` as "the canonical,
user-facing config doc" and the fourth touch of the mandatory 4-touch change — documents **27 of 46
fields**. The table's own preamble claims "Every field of `CongineConfig` is settable via `CONGINE_*`
environment variables", which is true, but the table does not list them.

The 19 fields that are fully wired and functional but absent from the README:

| | | |
|---|---|---|
| `cache_sweep_interval_seconds` | `semantic_max_breaches` | `jsonschema_draft` |
| `contract_source` | `contracts_dir` | `local_contracts_dir` |
| `telemetry_enabled` | `telemetry_queue_size` | `telemetry_batch_size` |
| `telemetry_max_retries` | `telemetry_backoff_base` | `telemetry_backoff_max` |
| `control_plane_http_timeout_seconds` | `snapshot_lock_timeout_seconds` | `log_redaction_enabled` |
| `max_schema_bytes` | `max_contract_files` | `max_stream_buffer_chars` |
| `max_http_response_bytes` | | |

Three of these are the most operationally significant switches in the whole surface:
`local_contracts_dir` (the standalone/air-gapped topology), `telemetry_enabled` (removes a thread
and a socket), and `jsonschema_draft` (fail-closed — a typo prevents the process from starting).
Recorded as debt D2 in §16.

One field is documented **incorrectly** rather than merely omitted: `drift_threshold` is described
as a p-value threshold; the code compares the D statistic (§11.3). Recorded as debt D15.
