/* ============================================================
   CONGINE Phase 0 — Architecture data model
   Single source of truth for every view.
   ============================================================ */

const LAYERS = [
  { id: 'L5', num: '05', name: 'Adapters & Access Points', dir: 'adapters/ · __init__.py',
    hue: 'var(--L5)', role: 'Framework adapters and the public consumption surface. Composition root + AOP entry.' },
  { id: 'L4', num: '04', name: 'Infrastructure', dir: 'infrastructure/',
    hue: 'var(--L4)', role: 'Concrete, side-effecting implementations of Layer-1 protocols. The only layer that touches I/O, threads, sockets and the clock.' },
  { id: 'L3', num: '03', name: 'Use Cases / Workflows', dir: 'usecases/',
    hue: 'var(--L3)', role: 'Stateless orchestration. Sequences domain logic and abstractions; owns no business rules and no I/O.' },
  { id: 'L2', num: '02', name: 'Domain / Business Kernel', dir: 'domain/',
    hue: 'var(--L2)', role: 'Pure, deterministic validation logic and immutable models. Zero framework imports. The innermost ring.' },
  { id: 'L1', num: '01', name: 'Repositories / Abstractions', dir: 'repositories/',
    hue: 'var(--L1)', role: 'Structural interfaces (typing.Protocol). The dependency-inversion seam every outer layer is wired through.' },
  { id: 'L0', num: '00', name: 'Global Shared', dir: 'config.py · exceptions.py',
    hue: 'var(--L0)', role: 'Cross-cutting immutable configuration and the canonical exception taxonomy. Imported by all, depends on none.' },
];

/* helper to keep signatures terse */
const m = (sig, doc) => ({ sig, doc });

const COMPONENTS = {

  /* ---------- L0 SHARED ---------- */
  config: {
    layer: 'L0', name: 'CongineConfig', file: 'config.py', kind: 'Frozen dataclass + Enums',
    role: 'Immutable runtime configuration assembled once at bootstrap and threaded read-only through every layer.',
    tags: [['frozen','frozen'],['','immutable']],
    dependsOn: [],
    members: [
      m('base_url, api_key, project_id, tenant_id: <span class="ty">str</span>', 'Control-plane coordinates + tenant identity used to scope every request.'),
      m('region: <span class="ty">Region</span>  ·  US | EU | APAC', 'Data-residency selector. EU pins Frankfurt for GDPR.'),
      m('validation_timeout_ms: <span class="ty">int</span> = 15', 'Hard ceiling for a single hot-path validation run.'),
      m('fail_mode: <span class="ty">FailMode</span> = DEGRADE', 'STRICT raises · DEGRADE logs+continues · SILENT swallows.'),
      m('cache_capacity: <span class="ty">int</span> = 500 · cache_ttl_seconds: <span class="ty">int</span> = 300', 'LFU sizing & per-entry TTL.'),
      m('<span class="kw">classmethod</span> from_env() -> CongineConfig', 'Hydrates the frozen instance from CONGINE_* environment variables.'),
    ],
    invariants: [
      'Declared frozen=True — any post-construction mutation raises FrozenInstanceError.',
      'Region / FailMode are str-Enums so values survive JSON round-trips and env parsing.',
      'No secret is logged: api_key is never placed in a TelemetryEvent or log extra.',
    ],
    code: `<span class="kw">@dataclass</span>(frozen=<span class="kw">True</span>)
<span class="kw">class</span> <span class="ty">CongineConfig</span>:
    base_url: <span class="ty">str</span>;  api_key: <span class="ty">str</span>
    project_id: <span class="ty">str</span>;  tenant_id: <span class="ty">str</span>
    region: <span class="ty">Region</span>
    validation_timeout_ms: <span class="ty">int</span> = <span class="st">15</span>
    fail_mode: <span class="ty">FailMode</span> = FailMode.DEGRADE
    cache_capacity: <span class="ty">int</span> = <span class="st">500</span>
    cache_ttl_seconds: <span class="ty">int</span> = <span class="st">300</span>

    <span class="kw">@classmethod</span>
    <span class="kw">def</span> <span class="fn">from_env</span>(cls) -> <span class="st">"CongineConfig"</span>:
        <span class="cm"># os.getenv(...) for every CONGINE_* key</span>
        ...</code>`,
  },

  exceptions: {
    layer: 'L0', name: 'CongineBaseException', file: 'exceptions.py', kind: 'Exception taxonomy',
    role: 'Canonical, catch-by-base exception tree. One root lets host code guard the entire SDK with a single except clause.',
    tags: [['','canonical']],
    dependsOn: [],
    members: [
      m('CongineBaseException', 'Tier-1 root. Every Congine error derives from it.'),
      m('├─ CongineValidationError', 'A contract breach or timeout fallback.'),
      m('├─ CongineContractNotFoundError', 'Schema/contract absent from storage.'),
      m('├─ CongineConfigurationError', 'Malformed or incomplete CongineConfig.'),
      m('├─ CongineSyncError', 'Control-plane synchronisation failure.'),
      m('├─ CongineCacheError', 'LFU cache structural fault.'),
      m('└─ CongineTelemetryError', 'Telemetry publish/drain failure.'),
      m('Tier-2 aliases', 'ContractBreachException · SchemaCacheMissException · ValidationTimeoutException · TenantIsolationViolationException → mapped onto Tier-1 for back-compat.'),
    ],
    invariants: [
      'All concrete errors inherit a single root → host code can `except CongineBaseException`.',
      'Aliases are assignment-bound to canonical classes, never independent subclasses.',
    ],
  },

  /* ---------- L1 PROTOCOLS ---------- */
  ISchemaStorage: {
    layer: 'L1', name: 'ISchemaStorage', file: 'repositories/schema_storage.py', kind: 'typing.Protocol',
    role: 'Read/write seam for cached schemas. Implemented by the in-memory LFU cache; consumed by the use case.',
    tags: [['proto','Protocol']],
    dependsOn: [],
    members: [
      m('get(contract_id: <span class="ty">str</span>) -> <span class="ty">Optional[Dict]</span>', 'Return live schema or None on miss / TTL-expiry.'),
      m('put(contract_id, schema, ttl_seconds) -> <span class="ty">None</span>', 'Insert with TTL; evicts LFU at capacity.'),
      m('clear() -> <span class="ty">None</span>', 'Flush all entries (tenant teardown).'),
      m('exists(contract_id: <span class="ty">str</span>) -> <span class="ty">bool</span>', 'Presence + freshness probe without mutating frequency.'),
    ],
    invariants: [
      'Structural — any class with these four methods satisfies it; no inheritance required.',
      'get() returning None is the canonical "cache-miss OR expired" signal.',
    ],
    code: `<span class="kw">class</span> <span class="ty">ISchemaStorage</span>(Protocol):
    <span class="kw">def</span> <span class="fn">get</span>(self, contract_id: <span class="ty">str</span>) -> <span class="ty">Optional</span>[<span class="ty">Dict</span>[<span class="ty">str</span>, <span class="ty">Any</span>]]: ...
    <span class="kw">def</span> <span class="fn">put</span>(self, contract_id: <span class="ty">str</span>,
            schema: <span class="ty">Dict</span>[<span class="ty">str</span>, <span class="ty">Any</span>],
            ttl_seconds: <span class="ty">int</span>) -> <span class="ty">None</span>: ...
    <span class="kw">def</span> <span class="fn">clear</span>(self) -> <span class="ty">None</span>: ...
    <span class="kw">def</span> <span class="fn">exists</span>(self, contract_id: <span class="ty">str</span>) -> <span class="ty">bool</span>: ...</code>`,
  },

  IContractRepository: {
    layer: 'L1', name: 'IContractRepository', file: 'repositories/contract_repository.py', kind: 'typing.Protocol',
    role: 'Source of truth for active contracts: async network fetch + synchronous disk-snapshot fallback for offline boot.',
    tags: [['proto','Protocol'],['async','async']],
    dependsOn: [],
    members: [
      m('<span class="kw">async</span> fetch_active_contracts() -> <span class="ty">List[Dict]</span>', 'GET control-plane; only awaited off the hot path.'),
      m('load_snapshot() -> <span class="ty">Optional[List[Dict]]</span>', 'Stale-OK disk read for offline bootstrap.'),
      m('save_snapshot(contracts) -> <span class="ty">None</span>', 'Atomic persist via tempfile + os.replace().'),
    ],
    invariants: [
      'Only the async method performs network I/O — it is never called on the guard hot-path.',
      'Snapshot read/write is filesystem-atomic so a crash mid-write cannot corrupt the cache seed.',
    ],
  },

  IEventBus: {
    layer: 'L1', name: 'IEventBus', file: 'repositories/event_bus.py', kind: 'typing.Protocol',
    role: 'Fire-and-forget telemetry sink. Publishing must never block or fail the caller.',
    tags: [['proto','Protocol']],
    dependsOn: [],
    members: [
      m('publish(event: <span class="ty">TelemetryEvent</span>) -> <span class="ty">None</span>', 'Non-blocking enqueue; drops silently when saturated.'),
    ],
    invariants: [
      'publish() is total: it returns in O(1) and raises nothing to the host.',
      'Back-pressure resolves toward dropping events, never blocking the hot-path.',
    ],
  },

  ILogger: {
    layer: 'L1', name: 'ILogger', file: 'repositories/logger.py', kind: 'typing.Protocol',
    role: 'Structured key-value logging seam, injected everywhere observability is needed.',
    tags: [['proto','Protocol']],
    dependsOn: [],
    members: [
      m('info / error / warning / debug(message: <span class="ty">str</span>, **kwargs) -> <span class="ty">None</span>', 'Level methods accepting arbitrary structured extras.'),
    ],
    invariants: [
      'Extras are arbitrary kwargs → callers attach context without a logger schema change.',
    ],
  },

  IValidator: {
    layer: 'L1', name: 'IValidator', file: 'domain/validator.py', kind: 'typing.Protocol',
    role: 'Validation-strategy seam. Declared alongside the domain; LocalValidator is its structural implementer.',
    tags: [['proto','Protocol']],
    dependsOn: ['models'],
    members: [
      m('validate(payload: <span class="ty">dict</span>, schema: <span class="ty">dict</span>) -> <span class="ty">ValidationResult</span>', 'Single method — any object exposing it is a validator.'),
    ],
    invariants: [
      'Lives at the domain seam so the use case depends on an abstraction, not LocalValidator directly.',
      'Enables alternate strategies (remote, cached, composite) without touching Layer 3.',
    ],
  },

  /* ---------- L2 DOMAIN ---------- */
  models: {
    layer: 'L2', name: 'Domain Models', file: 'domain/models.py', kind: 'Frozen dataclasses',
    role: 'Immutable value objects passed across every boundary. No behaviour beyond derivation helpers.',
    tags: [['frozen','frozen']],
    dependsOn: [],
    members: [
      m('BreachDetail(rule, field, message?)', 'One rule violation. field="&lt;root&gt;" for whole-payload faults.'),
      m('ValidationResult(status, breaches=(), duration_ms, degraded)', 'Outcome aggregate; .is_pass() derives from status.'),
      m('TelemetryEvent(contract_id, version, status, duration_ms, breach_details, created_at)', 'Mutable event record; __post_init__ stamps UTC time + empties.'),
    ],
    invariants: [
      'BreachDetail / ValidationResult are frozen — results cannot be tampered with downstream.',
      'breaches is a tuple (hashable, immutable) not a list.',
      'TelemetryEvent.__post_init__ guarantees created_at and breach_details are never None.',
    ],
    code: `<span class="kw">@dataclass</span>(frozen=<span class="kw">True</span>)
<span class="kw">class</span> <span class="ty">ValidationResult</span>:
    status: <span class="ty">str</span>                  <span class="cm"># "pass" | "fail"</span>
    breaches: <span class="ty">tuple</span> = ()
    duration_ms: <span class="ty">float</span> = <span class="st">0.0</span>
    degraded: <span class="ty">bool</span> = <span class="kw">False</span>
    <span class="kw">def</span> <span class="fn">is_pass</span>(self) -> <span class="ty">bool</span>:
        <span class="kw">return</span> self.status == <span class="st">"pass"</span></code>`,
  },

  RuleEngine: {
    layer: 'L2', name: 'RuleEngine', file: 'domain/validator.py', kind: 'Stateless static methods',
    role: 'The six pure validation taxons. Every method is a referentially-transparent function: payload + spec → breaches.',
    tags: [['','pure'],['','stateless']],
    dependsOn: ['models'],
    members: [
      m('FIELD_PRESENCE(payload, required) — dot-notation traversal', 'Walks "a.b.c" paths; missing leaf → breach.'),
      m('TYPE_MATCH(payload, properties) — numeric widening', 'bool⊄int; int↦number permitted; checks string/number/integer/boolean/object/array.'),
      m('ENUM_VALUES(payload, enum_map)', 'Value must be ∈ declared enum set.'),
      m('RANGE_CHECK(payload, range_map)', 'min ≤ value ≤ max inclusive bounds.'),
      m('NULL_GUARD(payload, null_forbidden)', 'Listed fields may not be None.'),
      m('REGEX_PATTERN(payload, pattern_map)', 're.fullmatch against compiled pattern.'),
    ],
    invariants: [
      'No method holds state, touches I/O, or mutates the payload — safe to run concurrently.',
      'TYPE_MATCH treats bool as NOT a valid int (Python bool⊂int trap explicitly closed).',
      'int satisfies a "number" spec (numeric widening); float never satisfies "integer".',
      'Each returns a fresh List[BreachDetail]; empty list = clean.',
    ],
    code: `<span class="kw">class</span> <span class="ty">RuleEngine</span>:
    <span class="kw">@staticmethod</span>
    <span class="kw">def</span> <span class="fn">TYPE_MATCH</span>(payload, props) -> <span class="ty">List</span>[<span class="ty">BreachDetail</span>]:
        out = []
        <span class="kw">for</span> f, spec <span class="kw">in</span> props.items():
            v = payload.get(f)
            <span class="kw">if</span> spec[<span class="st">"type"</span>] == <span class="st">"integer"</span>:
                ok = <span class="fn">isinstance</span>(v, <span class="ty">int</span>) <span class="kw">and not</span> <span class="fn">isinstance</span>(v, <span class="ty">bool</span>)
            ...
            <span class="kw">if not</span> ok: out.append(BreachDetail(<span class="st">"TYPE_MATCH"</span>, f))
        <span class="kw">return</span> out</code>`,
  },

  LocalValidator: {
    layer: 'L2', name: 'LocalValidator', file: 'domain/validator.py', kind: 'IValidator impl (composition)',
    role: 'Composes the six rules over a schema and measures wall-time. Rules are injected, never inherited.',
    tags: [['proto','IValidator']],
    dependsOn: ['RuleEngine','models'],
    members: [
      m('__init__(rules: <span class="ty">list</span> = None)', 'DI of [(name, fn)…]; defaults to all six RuleEngine taxons.'),
      m('validate(payload, schema) -> <span class="ty">ValidationResult</span>', 'Guards non-dict root, folds breaches, stamps duration_ms.'),
    ],
    invariants: [
      'Non-dict payload short-circuits to a single &lt;root&gt; TYPE_MATCH breach.',
      'Rule list is constructor-injected → custom rule sets without subclassing.',
      'Tracks evaluation time via perf_counter and writes it into the result.',
    ],
    code: `<span class="kw">class</span> <span class="ty">LocalValidator</span>:
    <span class="kw">def</span> <span class="fn">__init__</span>(self, rules: <span class="ty">list</span> = <span class="kw">None</span>):
        self.rules = rules <span class="kw">or</span> [
          (<span class="st">"FIELD_PRESENCE"</span>, RuleEngine.FIELD_PRESENCE),
          (<span class="st">"TYPE_MATCH"</span>,     RuleEngine.TYPE_MATCH),
          (<span class="st">"ENUM_VALUES"</span>,    RuleEngine.ENUM_VALUES),
          (<span class="st">"RANGE_CHECK"</span>,    RuleEngine.RANGE_CHECK),
          (<span class="st">"NULL_GUARD"</span>,     RuleEngine.NULL_GUARD),
          (<span class="st">"REGEX_PATTERN"</span>,  RuleEngine.REGEX_PATTERN)]

    <span class="kw">def</span> <span class="fn">validate</span>(self, payload, schema) -> <span class="ty">ValidationResult</span>:
        t0 = perf_counter()
        <span class="kw">if not</span> <span class="fn">isinstance</span>(payload, <span class="ty">dict</span>):
            <span class="kw">return</span> ValidationResult(<span class="st">"fail"</span>,
                (BreachDetail(<span class="st">"TYPE_MATCH"</span>, <span class="st">"&lt;root&gt;"</span>),))
        breaches = []
        <span class="kw">for</span> name, fn <span class="kw">in</span> self.rules:
            breaches += fn(payload, _spec(name, schema))
        dt = (perf_counter() - t0) * <span class="st">1000</span>
        <span class="kw">return</span> ValidationResult(
            <span class="st">"pass"</span> <span class="kw">if not</span> breaches <span class="kw">else</span> <span class="st">"fail"</span>,
            <span class="fn">tuple</span>(breaches), duration_ms=dt)</code>`,
  },

  /* ---------- L3 USECASE ---------- */
  ValidateContractUseCase: {
    layer: 'L3', name: 'ValidateContractUseCase', file: 'usecases/validate_contract_usecase.py', kind: 'Orchestrator',
    role: 'The single workflow of Phase 0: fetch schema → bounded validate → fire telemetry. All five dependencies are constructor-injected abstractions.',
    tags: [['','orchestration']],
    dependsOn: ['ISchemaStorage','LocalValidator','IEventBus','ILogger','ValidationTimer'],
    members: [
      m('__init__(schema_storage: <span class="ty">ISchemaStorage</span>, validator: <span class="ty">IValidator</span>, event_bus: <span class="ty">IEventBus</span>, logger: <span class="ty">ILogger</span>, timer: <span class="ty">ValidationTimer</span>, timeout_ms=15)', 'Pure DI — every param is a Layer-1 protocol or injected utility.'),
      m('execute(payload, contract_id, contract_version) -> <span class="ty">ValidationResult</span>', '3-step: storage.get → timer.run_with_timeout(validate) → bus.publish.'),
    ],
    invariants: [
      'Holds NO concrete reference — only protocol-typed fields → trivially mockable.',
      'A missing schema raises CongineContractNotFoundError before any rule runs.',
      'Timeout or exception inside validate() degrades to a fail result (degraded=True), never propagates.',
      'Telemetry publish is the final, fire-and-forget step and cannot alter the returned result.',
    ],
    code: `<span class="kw">def</span> <span class="fn">execute</span>(self, payload, contract_id, version):
    schema = self.schema_storage.<span class="fn">get</span>(contract_id)
    <span class="kw">if</span> schema <span class="kw">is</span> <span class="kw">None</span>:
        self.logger.<span class="fn">error</span>(<span class="st">"schema_miss"</span>, contract_id=contract_id)
        <span class="kw">raise</span> CongineContractNotFoundError(contract_id)
    <span class="kw">try</span>:
        result = self.timer.<span class="fn">run_with_timeout</span>(
            <span class="kw">lambda</span>: self.validator.<span class="fn">validate</span>(payload, schema),
            self.timeout_ms)
    <span class="kw">except</span> (TimeoutError, Exception):
        result = ValidationResult(<span class="st">"fail"</span>, degraded=<span class="kw">True</span>)
    self.event_bus.<span class="fn">publish</span>(_to_event(result, contract_id, version))
    <span class="kw">return</span> result</code>`,
  },

  /* ---------- L4 INFRASTRUCTURE ---------- */
  LFUCache: {
    layer: 'L4', name: 'LFUCache', file: 'infrastructure/lfu_cache.py', kind: 'ISchemaStorage impl · O(1)',
    role: 'In-process O(1) LFU cache with per-entry TTL and a 30s daemon sweeper. The hot-path schema source — zero network.',
    tags: [['proto','ISchemaStorage'],['thread','RLock'],['','O(1)']],
    dependsOn: ['ISchemaStorage'],
    members: [
      m('_key_to_value: <span class="ty">dict</span>', 'contract_id → (schema, expire_at).'),
      m('_key_to_freq: <span class="ty">dict</span>', 'contract_id → access count.'),
      m('_freq_to_keys: <span class="ty">dict[int, OrderedDict]</span>', 'frequency → LRU chain of keys at that frequency.'),
      m('_min_freq: <span class="ty">int</span> · _lock: <span class="ty">RLock</span>', 'Eviction pointer + reentrant mutex.'),
      m('get / put / exists / clear', 'All O(1); get() bumps frequency and re-links chains.'),
      m('_evict_lfu() · _increment_freq(k)', 'Pop head of _freq_to_keys[_min_freq]; promote on access.'),
    ],
    invariants: [
      'get / put are amortised O(1) — no scans, ever.',
      'Eviction removes the LRU key inside the least-frequently-used bucket.',
      'Every mutating path is wrapped in RLock → re-entrant from the sweeper thread.',
      'A 30s daemon thread proactively purges TTL-expired keys; get() also lazy-expires.',
    ],
    code: `<span class="kw">def</span> <span class="fn">get</span>(self, key):
    <span class="kw">with</span> self._lock:
        node = self._key_to_value.get(key)
        <span class="kw">if</span> node <span class="kw">is</span> <span class="kw">None</span>: <span class="kw">return</span> <span class="kw">None</span>
        schema, expire = node
        <span class="kw">if</span> time.time() > expire:
            self.<span class="fn">_evict_key</span>(key); <span class="kw">return</span> <span class="kw">None</span>
        self.<span class="fn">_increment_freq</span>(key)   <span class="cm"># O(1) re-link</span>
        <span class="kw">return</span> schema</code>`,
  },

  HttpContractRepository: {
    layer: 'L4', name: 'HttpContractRepository', file: 'infrastructure/http_contract_repository.py', kind: 'IContractRepository impl',
    role: 'Async control-plane client + atomic snapshot persistence. Seeds the cache at boot; never invoked on the hot-path.',
    tags: [['proto','IContractRepository'],['async','async']],
    dependsOn: ['IContractRepository','config'],
    members: [
      m('<span class="kw">async</span> fetch_active_contracts()', 'httpx GET /api/v1/contracts/active with X-API-Key / X-Project-ID / X-Tenant-ID headers, 10s timeout.'),
      m('load_snapshot()', 'Reads /tmp/congine_snapshot.json; tolerant of missing/corrupt file → None.'),
      m('save_snapshot(contracts)', 'mkstemp → write → os.replace() atomic swap; cleans temp on failure.'),
    ],
    invariants: [
      'Tenant headers are attached to every outbound request (isolation at the wire).',
      'Snapshot writes are crash-atomic — readers never observe a half-written file.',
      'All network failure is caught and degraded to snapshot; boot never hard-fails on a cold network.',
    ],
  },

  QueueEventBus: {
    layer: 'L4', name: 'QueueEventBus', file: 'infrastructure/queue_event_bus.py', kind: 'IEventBus impl · worker',
    role: 'Thread-safe fire-and-forget telemetry: bounded queue + daemon drain worker with backoff and an atexit flush.',
    tags: [['proto','IEventBus'],['thread','queue.Queue']],
    dependsOn: ['IEventBus'],
    members: [
      m('_queue: <span class="ty">queue.Queue</span>(maxsize=10_000)', 'Bounded buffer; full → drop.'),
      m('publish(event)', 'put_nowait; on queue.Full logs+drops (graceful degradation).'),
      m('_drain_loop()', 'Daemon: get(timeout=1) → atomic chunk POST → exponential backoff on failure.'),
      m('_drain_on_exit()', 'atexit hook drains remaining events before interpreter shutdown.'),
    ],
    invariants: [
      'publish() is O(1) and never blocks the producer — saturation drops, not stalls.',
      'Worker is a daemon thread → never blocks process exit, but atexit flushes first.',
      'Transient ship failures retry with exponential backoff; permanent failure drops the chunk.',
    ],
  },

  StructuredLogger: {
    layer: 'L4', name: 'StructuredLogger', file: 'infrastructure/logger.py', kind: 'ILogger impl',
    role: 'Zero-dependency JSON-lines logger to stdout. Emits one structured record per call.',
    tags: [['proto','ILogger']],
    dependsOn: ['ILogger'],
    members: [
      m('_log(level, message, **kwargs)', 'Builds {timestamp, level, logger, message, **extras} and json.dumps to stdout.'),
      m('info / error / warning / debug', 'Thin level wrappers over _log.'),
    ],
    invariants: [
      'Every line is a self-contained JSON object (log-shipper friendly).',
      'UTC ISO-8601 timestamp stamped per record.',
    ],
  },

  ValidationTimer: {
    layer: 'L4', name: 'ValidationTimer', file: 'infrastructure/timer.py', kind: 'Timeout utility',
    role: 'Cross-platform (Windows-safe) timeout via a ThreadPoolExecutor — not signal.alarm. Enforces the sub-200ms budget.',
    tags: [['thread','ThreadPool']],
    dependsOn: [],
    members: [
      m('__init__()', 'ThreadPoolExecutor(max_workers=10, prefix="congine_timer"); atexit cleanup registered.'),
      m('run_with_timeout(func, timeout_ms) -> <span class="ty">Any</span>', 'submit→future.result(timeout); raises TimeoutError on overrun.'),
      m('_cleanup()', 'shutdown(wait=False) at process exit.'),
    ],
    invariants: [
      'Uses futures not signals → works on every OS and inside non-main threads.',
      'A timed-out thread cannot be force-killed; it is abandoned and the pool is bounded to cap leakage.',
    ],
  },

  /* ---------- L5 ADAPTERS ---------- */
  ServiceContainer: {
    layer: 'L5', name: 'ServiceContainer', file: 'adapters/dependency_injection.py', kind: 'Composition root',
    role: 'The single place concrete classes are named. Assembles infrastructure → domain → use case, bottom-up, then exposes the wired graph.',
    tags: [['','composition root']],
    dependsOn: ['StructuredLogger','ValidationTimer','LFUCache','HttpContractRepository','QueueEventBus','LocalValidator','ValidateContractUseCase','config'],
    members: [
      m('__init__(config: <span class="ty">CongineConfig</span>)', 'Instantiates L4 concretes, then the L2 validator, then injects all into the L3 use case.'),
      m('<span class="kw">classmethod</span> from_env()', 'CongineConfig.from_env() → cls(config). The 1-line bootstrap.'),
      m('.validate_contract_usecase', 'The fully-wired entry the guard decorator calls.'),
    ],
    invariants: [
      'Build order is strict: Infrastructure → Domain → Use Case (inner deps exist before injection).',
      'No global/singleton state — multiple isolated containers may coexist (per-tenant).',
      'It is the ONLY module permitted to import concrete Layer-4 classes.',
    ],
    code: `<span class="kw">class</span> <span class="ty">ServiceContainer</span>:
    <span class="kw">def</span> <span class="fn">__init__</span>(self, config: <span class="ty">CongineConfig</span>):
        self.logger  = <span class="fn">StructuredLogger</span>(<span class="st">"congine"</span>)
        self.timer   = <span class="fn">ValidationTimer</span>()
        self.schema_storage = <span class="fn">LFUCache</span>(
            config.cache_capacity, config.cache_ttl_seconds)
        self.contract_repository = <span class="fn">HttpContractRepository</span>(config, self.logger)
        self.event_bus = <span class="fn">QueueEventBus</span>(self.logger)
        self.validator = <span class="fn">LocalValidator</span>()          <span class="cm"># default 6 rules</span>
        self.validate_contract_usecase = <span class="fn">ValidateContractUseCase</span>(
            self.schema_storage, self.validator, self.event_bus,
            self.logger, self.timer, config.validation_timeout_ms)</code>`,
  },

  congine_guard: {
    layer: 'L5', name: '@congine_guard', file: 'adapters/guard.py', kind: 'AOP decorator',
    role: 'The public aspect. Wraps any sync or async target, runs it, validates the output against a contract, and returns {output, validation_result}.',
    tags: [['async','sync+async']],
    dependsOn: ['ServiceContainer','ValidateContractUseCase'],
    members: [
      m('congine_guard(contract_id, version="latest", container=None)', 'Factory; resolves container or ServiceContainer.from_env().'),
      m('sync_wrapper / async_wrapper', 'Both functools.wraps(fn); async awaits the target then runs the (sync) validation.'),
      m('iscoroutinefunction(fn) switch', 'Picks the native wrapper at decoration time — no cross-paradigm blocking.'),
    ],
    invariants: [
      'asyncio.iscoroutinefunction(fn) chooses the wrapper → an async target stays awaitable, a sync target stays direct-call.',
      'functools.wraps preserves __name__/__doc__/signature for introspection.',
      'Validation is synchronous and CPU-bound → it never schedules onto or blocks the event loop incorrectly.',
      'Decorator overhead off the validation call is effectively zero allocation on the steady-state path.',
    ],
    code: `<span class="kw">def</span> <span class="fn">congine_guard</span>(contract_id, version=<span class="st">"latest"</span>, container=<span class="kw">None</span>):
    ctx = container <span class="kw">or</span> ServiceContainer.<span class="fn">from_env</span>()
    <span class="kw">def</span> <span class="fn">decorator</span>(fn):
        <span class="kw">@functools.wraps</span>(fn)
        <span class="kw">def</span> <span class="fn">sync_wrapper</span>(*a, **k):
            out = fn(*a, **k)
            vr = ctx.validate_contract_usecase.<span class="fn">execute</span>(out, contract_id, version)
            <span class="kw">return</span> {<span class="st">"output"</span>: out, <span class="st">"validation_result"</span>: vr}
        <span class="kw">@functools.wraps</span>(fn)
        <span class="kw">async def</span> <span class="fn">async_wrapper</span>(*a, **k):
            out = <span class="kw">await</span> fn(*a, **k)
            vr = ctx.validate_contract_usecase.<span class="fn">execute</span>(out, contract_id, version)
            <span class="kw">return</span> {<span class="st">"output"</span>: out, <span class="st">"validation_result"</span>: vr}
        <span class="kw">return</span> async_wrapper <span class="kw">if</span> asyncio.<span class="fn">iscoroutinefunction</span>(fn) <span class="kw">else</span> sync_wrapper
    <span class="kw">return</span> decorator</code>`,
  },
};

/* layer → ordered component ids (for the Layer Map) */
const LAYER_MEMBERS = {
  L5: ['ServiceContainer', 'congine_guard'],
  L4: ['LFUCache', 'HttpContractRepository', 'QueueEventBus', 'StructuredLogger', 'ValidationTimer'],
  L3: ['ValidateContractUseCase'],
  L2: ['models', 'RuleEngine', 'LocalValidator'],
  L1: ['ISchemaStorage', 'IContractRepository', 'IEventBus', 'ILogger'],
  L0: ['config', 'exceptions'],
};

window.CONGINE = { LAYERS, COMPONENTS, LAYER_MEMBERS };
