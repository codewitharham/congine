/* ============================================================
   CONGINE Phase 0 — Workflows · LFU cache · ADR renderers
   ============================================================ */
(function () {
  const H = { L5:'var(--L5)', L4:'var(--L4)', L3:'var(--L3)', L2:'var(--L2)', L1:'var(--L1)', L0:'var(--L0)', sig:'var(--signal)' };
  const $ = (s, r = document) => r.querySelector(s);

  /* ---------- generic step renderer ---------- */
  function step(s, n, total) {
    const cls = [s.hot ? 'hot' : '', s.term ? 'term' : ''].join(' ').trim();
    const branch = s.branch ? `
      <div class="st-branch">
        <div class="st-arm hit"><b>${s.branch.a.k}</b>${s.branch.a.v}</div>
        <div class="st-arm miss"><b>${s.branch.b.k}</b>${s.branch.b.v}</div>
      </div>` : '';
    const meta = (s.meta || []).map(t => `<span class="tag ${t[0] || ''}">${t[1] || t}</span>`).join('');
    const label = s.term ? '✓' : n;
    return `
      <div class="step ${cls}">
        <div class="st-gutter">
          <div class="st-dot">${label}</div>
          <div class="st-line"></div>
        </div>
        <div class="st-card" style="--accent:${s.hue || 'var(--ink-2)'}">
          <div class="sc-actor">${s.actor}</div>
          <div class="sc-title">${s.title}</div>
          <div class="sc-desc">${s.desc}</div>
          ${meta ? `<div class="sc-meta">${meta}</div>` : ''}
          ${branch}
        </div>
      </div>`;
  }
  function renderFlow(mount, lane, steps) {
    mount.innerHTML = `<div class="flow"><div class="flow-lane-head">${lane}</div>` +
      steps.map((s, i) => step(s, i + 1, steps.length)).join('') + `</div>`;
  }

  /* ============================================================
     WORKFLOW A — bootstrap
     ============================================================ */
  const FLOW_A = [
    { actor: 'HOST · L5', hue: H.sig,
      title: 'Bootstrap trigger',
      desc: 'Host process calls <code>ServiceContainer.from_env()</code> (or the guard lazily resolves one on first decoration). One-time, synchronous, off the hot-path.',
      meta: [['','cold start'],['thread','main thread']] },
    { actor: 'CongineConfig · L0', hue: H.L0,
      title: 'Hydrate frozen configuration',
      desc: '<code>from_env()</code> reads every <code>CONGINE_*</code> variable into a <code>frozen=True</code> dataclass — base_url, keys, region, timeout_ms, cache sizing. Immutable for the process lifetime.',
      meta: [['frozen','frozen'],['','env-loaded']] },
    { actor: 'ServiceContainer · L5', hue: H.L5,
      title: 'Assemble infrastructure (L4)',
      desc: 'Bottom-up build: <code>StructuredLogger</code> → <code>ValidationTimer</code> (ThreadPool) → <code>LFUCache(capacity, ttl)</code>. The cache spawns its <b>30 s daemon sweeper</b>.',
      meta: [['thread','daemon ×1'],['','O(1) cache up']] },
    { actor: 'ServiceContainer · L5', hue: H.L5,
      title: 'Provision channels',
      desc: 'Instantiate <code>HttpContractRepository(config)</code> and <code>QueueEventBus</code> — the latter starts its <b>drain worker</b> and registers an <code>atexit</code> flush hook.',
      meta: [['thread','daemon ×2'],['async','atexit drain']] },
    { actor: 'IContractRepository · L1', hue: H.L1,
      title: 'Prime schema cache — offline-safe',
      desc: 'Attempt <code>await fetch_active_contracts()</code> against the control plane. The outcome forks the boot path:',
      branch: {
        a: { k: 'NETWORK OK ▸', v: 'persist <code>save_snapshot()</code> atomically, then seed cache.' },
        b: { k: 'OFFLINE ▸', v: '<code>load_snapshot()</code> from /tmp — stale-OK seed, boot still succeeds.' },
      },
      meta: [['async','off hot-path'],['','atomic write']] },
    { actor: 'LFUCache · L4', hue: H.L4,
      title: 'Seed entries',
      desc: 'For each active contract: <code>put(contract_id, schema, ttl)</code>. All inserts are O(1); frequency buckets initialise at 1.',
      meta: [['','O(1) put']] },
    { actor: 'Domain + Use Case · L2/L3', hue: H.L3,
      title: 'Wire the kernel',
      desc: 'Construct <code>LocalValidator()</code> with the default six rules, then <code>ValidateContractUseCase(...)</code> with every dependency injected by constructor.',
      meta: [['','DI complete']] },
    { actor: 'ServiceContainer · L5', hue: H.L5, term: true,
      title: 'Container ready · guard armed',
      desc: 'The wired object graph is returned. The hot-path can now run with <b>zero network calls</b>. Steady state begins.',
      meta: [['','ready']] },
  ];

  /* ============================================================
     WORKFLOW B — hot-path guard
     ============================================================ */
  const FLOW_B = [
    { actor: '@congine_guard · L5', hue: H.sig, hot: true,
      title: 'Interception',
      desc: 'A guarded call enters the wrapper chosen at <i>decoration</i> time via <code>asyncio.iscoroutinefunction(fn)</code> — sync stays direct-call, async stays awaitable. No cross-paradigm blocking.',
      meta: [['async','sync | async'],['','functools.wraps']] },
    { actor: '@congine_guard · L5', hue: H.sig, hot: true,
      title: 'Execute target',
      desc: 'Run the wrapped function (<code>await</code> if coroutine) to produce the candidate <code>output</code> payload that must satisfy the contract.',
      meta: [['','native exec']] },
    { actor: 'ContextVar · L5', hue: H.L5, hot: true,
      title: 'Tenant / context isolation',
      desc: 'Read task-scoped <code>contextvars.ContextVar</code> for tenant + request scope — correct under both threads and concurrent asyncio tasks, unlike <code>threading.local</code>.',
      meta: [['thread','task-scoped']] },
    { actor: 'ISchemaStorage → LFUCache · L1/L4', hue: H.L4, hot: true,
      title: 'Resolve schema',
      desc: 'Use case calls <code>schema_storage.get(contract_id)</code> — a single O(1) poll of the in-process cache:',
      branch: {
        a: { k: 'CACHE HIT ▸', v: 'fresh schema returned; frequency bumped, chains re-linked O(1).' },
        b: { k: 'MISS / EXPIRED ▸', v: '<code>None</code> → raise <code>CongineContractNotFoundError</code>, degrade per <code>fail_mode</code>.' },
      },
      meta: [['','O(1) get'],['','zero network']] },
    { actor: 'ValidationTimer · L4', hue: H.L4, hot: true,
      title: 'Bounded execution',
      desc: 'Validation runs inside <code>run_with_timeout(fn, timeout_ms)</code>. Overrun raises <code>TimeoutError</code> → a <code>degraded=True</code> fail result. The sub-200 ms p99 budget is enforced here.',
      meta: [['thread','ThreadPool'],['','timeout 15ms']] },
    { actor: 'LocalValidator · L2', hue: H.L2, hot: true,
      title: 'Apply six rule taxons',
      desc: 'Pure fold over FIELD_PRESENCE · TYPE_MATCH · ENUM_VALUES · RANGE_CHECK · NULL_GUARD · REGEX_PATTERN. Deterministic, stateless, allocation-light.',
      branch: {
        a: { k: 'PASS ▸', v: 'no breaches → <code>ValidationResult("pass")</code>.' },
        b: { k: 'FAIL ▸', v: 'breaches collected with field + rule provenance.' },
      },
      meta: [['','pure'],['','6 rules']] },
    { actor: 'Patch engine · L2', hue: H.L2,
      title: 'Build RFC-6902 diff (on breach)',
      desc: 'Breaches are reduced into a structural JSON-Patch diff describing the deviation between payload and contract — the remediation artifact.',
      meta: [['','RFC 6902']] },
    { actor: 'IEventBus → QueueEventBus · L1/L4', hue: H.L4,
      title: 'Fire-and-forget telemetry',
      desc: '<code>event_bus.publish(TelemetryEvent)</code> enqueues in O(1) and returns instantly. The daemon worker ships it; a full queue drops silently — never blocks the caller.',
      meta: [['','non-blocking'],['thread','bg queue']] },
    { actor: '@congine_guard · L5', hue: H.sig, term: true,
      title: 'Return safe payload',
      desc: 'Hand <code>{ output, validation_result }</code> back to host code. Total hot-path: in-process, bounded, no network.',
      meta: [['','&lt; 200 ms p99']] },
  ];

  /* ============================================================
     LFU CACHE structure
     ============================================================ */
  function buildLFU() {
    const mount = $('#lfu');
    mount.innerHTML = `
      <div class="lfu-wrap">
        <div class="lfu-diagram">
          <div class="lfu-struct">
            <div class="ls-h">_key_to_value : dict</div>
            <div class="ls-sub">contract_id → (schema, expire_at)</div>
            <div class="freq-col">
              <div class="chain">
                <span class="cell">sentiment-v1 → (schema, t+300)</span>
              </div>
              <div class="chain">
                <span class="cell">toxicity-v1 → (schema, t+300)</span>
                <span class="cell" style="margin-left:10px">pricing-v4 → (schema, t+120)</span>
              </div>
              <div class="chain">
                <span class="cell lru">pii-v2 → (schema, t+15)</span>
                <span class="chain-tag">◂ nearest TTL expiry</span>
              </div>
            </div>
          </div>

          <div class="lfu-struct">
            <div class="ls-h">_key_to_freq : dict</div>
            <div class="ls-sub">contract_id → access_count</div>
            <div class="chain" style="gap:10px;flex-wrap:wrap">
              <span class="cell">sentiment-v1 : <b style="color:var(--blue)">5</b></span>
              <span class="cell">pricing-v4 : <b style="color:var(--blue)">3</b></span>
              <span class="cell">toxicity-v1 : <b style="color:var(--blue)">3</b></span>
              <span class="cell evict">pii-v2 : <b>1</b></span>
            </div>
          </div>

          <div class="lfu-struct">
            <div class="ls-h">_freq_to_keys : dict[int, OrderedDict]</div>
            <div class="ls-sub">frequency → LRU chain of keys at that frequency</div>
            <div class="freq-col">
              <div class="freq-row">
                <div class="freq-badge min">freq<br><b>1</b><br><span style="font-size:8px">_min_freq</span></div>
                <div class="chain">
                  <span class="cell evict">pii-v2</span>
                  <span class="chain-tag">◂ LRU head · eviction victim</span>
                </div>
              </div>
              <div class="freq-row">
                <div class="freq-badge">freq<br><b>3</b></div>
                <div class="chain">
                  <span class="cell lru">toxicity-v1</span><span class="lnk"></span>
                  <span class="cell">pricing-v4</span>
                  <span class="chain-tag">LRU ▸ MRU</span>
                </div>
              </div>
              <div class="freq-row">
                <div class="freq-badge">freq<br><b>5</b></div>
                <div class="chain">
                  <span class="cell">sentiment-v1</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="lfu-side">
          <div class="op">
            <h5>get(key)<span class="bigO">O(1)</span></h5>
            <ol>
              <li>Acquire <code>RLock</code>; look up <code>_key_to_value[key]</code>.</li>
              <li>If absent or <code>now &gt; expire_at</code> → evict &amp; return <code>None</code>.</li>
              <li><code>_increment_freq(key)</code>: move key from bucket <code>f</code> to <code>f+1</code>, append at MRU.</li>
              <li>If old bucket emptied and equalled <code>_min_freq</code> → <code>_min_freq += 1</code>.</li>
            </ol>
          </div>
          <div class="op">
            <h5>put(key, schema, ttl)<span class="bigO">O(1)</span></h5>
            <ol>
              <li>If at <code>capacity</code> → <code>_evict_lfu()</code> first.</li>
              <li>Store <code>(schema, time()+ttl)</code>; set freq = 1; append to bucket 1.</li>
              <li>Reset <code>_min_freq = 1</code>.</li>
            </ol>
          </div>
          <div class="op">
            <h5>_evict_lfu()<span class="bigO">O(1)</span></h5>
            <ol>
              <li>Pop LRU head of <code>_freq_to_keys[_min_freq]</code>.</li>
              <li>Delete from all three dicts — no scan, ever.</li>
            </ol>
          </div>
          <div class="op daemon">
            <h5>sweeper daemon<span class="bigO">30 s</span></h5>
            <ol>
              <li>Background thread wakes every 30 s under <code>RLock</code>.</li>
              <li>Purges TTL-expired keys proactively; <code>get()</code> also lazy-expires on read.</li>
            </ol>
          </div>
        </div>
      </div>`;
  }

  /* ============================================================
     ADR
     ============================================================ */
  const ADRS = [
    { id: '01', title: 'Structural typing over nominal inheritance',
      sub: 'typing.Protocol  vs  abc.ABC',
      context: 'Layer-1 seams must be implementable by infrastructure without importing the abstraction — and trivially mockable in tests without a class hierarchy.',
      decision: 'Define every boundary as a <code>typing.Protocol</code>. Conformance is by shape: any object with the right methods satisfies it. No <code>register()</code>, no base class, no import coupling.',
      consequence: 'Implementations in Layer 4 depend on <i>nothing</i> from Layer 1; test doubles are plain objects. The cost — conformance is checked structurally, so a typo surfaces at type-check, not import.' },
    { id: '02', title: 'In-memory O(1) LFU + TTL over a network cache',
      sub: 'custom dual-linked LFU  vs  Redis / plain dict',
      context: 'The hot-path forbids network calls and demands sub-200 ms p99. A naïve dict has no eviction or freshness; a network cache reintroduces the very latency and dependency we must remove.',
      decision: 'Hand-roll a three-structure O(1) LFU (key→value, key→freq, freq→OrderedDict) with per-entry TTL and a 30 s sweeper, all guarded by a single <code>RLock</code>.',
      consequence: 'Constant-time reads with bounded memory and zero external dependency. The cost — cache is process-local, so coherence across workers is explicitly out of Phase-0 scope.' },
    { id: '03', title: 'Task-scoped context over thread-local storage',
      sub: 'contextvars.ContextVar  vs  threading.local',
      context: 'The guard runs under both synchronous threads and concurrent <code>asyncio</code> tasks. Tenant isolation must follow the logical unit of work, not the OS thread.',
      decision: 'Carry tenant + request scope in <code>contextvars.ContextVar</code>, which the asyncio event loop copies per-task and restores across <code>await</code> boundaries.',
      consequence: 'Isolation is correct on a shared event-loop thread where many tenants interleave — a guarantee <code>threading.local</code> cannot make. The cost — contributors must set/reset context at task boundaries, not thread spawn.' },
  ];

  function buildADR() {
    $('#adr').innerHTML = `<div class="adr-grid">` + ADRS.map(a => `
      <div class="adr">
        <div class="adr-top">
          <div class="adr-id">${a.id}</div>
          <h3>${a.title}<small>${a.sub}</small></h3>
          <span class="adr-status">Accepted</span>
        </div>
        <div class="adr-body">
          <div class="adr-cell"><div class="ac-k">Context</div><p>${a.context}</p></div>
          <div class="adr-cell decision"><div class="ac-k">Decision</div><p>${a.decision}</p></div>
          <div class="adr-cell"><div class="ac-k">Consequence</div><p>${a.consequence}</p></div>
        </div>
      </div>`).join('') + `</div>`;
  }

  /* ---------- public ---------- */
  function build() {
    renderFlow($('#flowA'), 'Lifecycle ▸ one-time, synchronous, off hot-path', FLOW_A);
    renderFlow($('#flowB'), 'Lifecycle ▸ steady-state, per-call, in-process', FLOW_B);
    buildLFU();
    buildADR();
  }
  function redraw() { /* workflows use CSS connectors — no SVG redraw needed */ }

  window.FLOWS = { build, redraw };
})();
