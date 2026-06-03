/* ============================================================
   CONGINE Phase 0 — application controller
   Tabs · drawer · layer map · dependency map · wire highlight
   ============================================================ */
(function () {
  const { LAYERS, COMPONENTS, LAYER_MEMBERS } = window.CONGINE;
  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const HUE = { L5:'var(--L5)', L4:'var(--L4)', L3:'var(--L3)', L2:'var(--L2)', L1:'var(--L1)', L0:'var(--L0)' };
  const LAYER_NAME = Object.fromEntries(LAYERS.map(l => [l.id, l.name]));

  /* ---------------------------------------------------------
     DRAWER
     --------------------------------------------------------- */
  const drawer = $('#drawer'), scrim = $('#scrim');

  function memberRow(mm) {
    return `<div class="member"><div class="m-sig">${mm.sig}</div>${mm.doc ? `<div class="m-doc">${mm.doc}</div>` : ''}</div>`;
  }

  function openDrawer(id) {
    const c = COMPONENTS[id];
    if (!c) return;
    const hue = HUE[c.layer];
    drawer.style.setProperty('--accent', hue);
    $('#d-layer').textContent = `Layer ${c.layer.slice(1)} · ${LAYER_NAME[c.layer]}`;
    $('#d-layer').style.color = hue;
    $('#d-name').textContent = c.name;
    $('#d-file').textContent = c.file + '  ·  ' + c.kind;

    let html = `<div class="d-sect"><p class="d-role">${c.role}</p>`;
    if (c.tags && c.tags.length) {
      html += `<div class="n-tags" style="margin-top:12px">` +
        c.tags.map(t => `<span class="tag ${t[0]}">${t[1]}</span>`).join('') + `</div>`;
    }
    html += `</div>`;

    if (c.members && c.members.length) {
      html += `<div class="d-sect"><div class="eyebrow">Members · Contract</div>` +
        c.members.map(memberRow).join('') + `</div>`;
    }
    if (c.code) {
      html += `<div class="d-sect"><div class="eyebrow">Reference Implementation</div>` +
        `<div class="codeblock"><pre><code>${c.code}</pre></div></div>`;
    }
    if (c.invariants && c.invariants.length) {
      html += `<div class="d-sect"><div class="eyebrow">Implementation Invariants</div>` +
        c.invariants.map((iv, i) =>
          `<div class="invariant"><span class="iv-n">I${String(i + 1).padStart(2, '0')}</span><span>${iv}</span></div>`
        ).join('') + `</div>`;
    }
    if (c.dependsOn && c.dependsOn.length) {
      html += `<div class="d-sect"><div class="eyebrow">Depends On</div><div class="n-tags">` +
        c.dependsOn.map(d => {
          const dc = COMPONENTS[d];
          return `<span class="tag" data-jump="${d}" style="cursor:pointer;border-color:${HUE[dc?.layer]||'var(--line)'}">${dc ? dc.name : d}</span>`;
        }).join('') + `</div></div>`;
    }

    $('#d-body').innerHTML = html;
    $$('#d-body [data-jump]').forEach(t =>
      t.addEventListener('click', () => openDrawer(t.dataset.jump)));
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    scrim.classList.add('open');
  }
  function closeDrawer() {
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    scrim.classList.remove('open');
  }
  $('#d-close').addEventListener('click', closeDrawer);
  scrim.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

  /* ---------------------------------------------------------
     OVERVIEW — dependency ladder
     --------------------------------------------------------- */
  function buildLadder() {
    const el = $('#ladder');
    el.innerHTML = LAYERS.map(l => `
      <div class="ladder-row" style="--lr-hue:${l.hue}">
        <div class="lr-bar"></div>
        <div class="lr-num">${l.num}<small>${l.id}</small></div>
        <div class="lr-body"><b>${l.name}</b><span>${l.role}</span></div>
        <div class="lr-dir">${l.dir}</div>
      </div>`).join('') +
      `<div class="ladder-arrow"><span>OUTER</span><div class="la-track"></div><span>▼</span><div class="la-track"></div><span style="color:var(--signal)">INNER</span></div>`;
  }

  /* ---------------------------------------------------------
     LAYER MAP
     --------------------------------------------------------- */
  let layerWires = null;
  function buildLayerMap() {
    const root = $('#layermap');
    let html = '';
    LAYERS.forEach((l, i) => {
      const nodes = (LAYER_MEMBERS[l.id] || []).map(id => {
        const c = COMPONENTS[id];
        const tags = (c.tags || []).slice(0, 2)
          .map(t => `<span class="tag ${t[0]}">${t[1]}</span>`).join('');
        return `
          <div class="node" data-id="${id}" style="--accent:${l.hue}">
            <div class="n-head">
              <span class="n-name">${c.name}</span>
            </div>
            <div class="n-role">${c.kind}</div>
            <div class="n-tags">${tags}</div>
          </div>`;
      }).join('');
      html += `
        <div class="band" style="--band-hue:${l.hue}">
          <div class="band-rail">
            <div class="br-num">LAYER ${l.num} · ${l.id}</div>
            <div class="br-name">${l.name}</div>
            <div class="br-dir">${l.dir}</div>
            <div class="br-role">${l.role}</div>
          </div>
          <div class="band-nodes">${nodes}</div>
        </div>`;
      if (i < LAYERS.length - 1) html += `<div class="band-sep"><i>depends ▾ inward</i></div>`;
    });
    root.innerHTML = html;
    layerWires = window.Wires(root);
    layerWires.svg.style.zIndex = '6';   /* above opaque bands so hover edges are visible */

    $$('.node', root).forEach(node => {
      node.addEventListener('click', () => openDrawer(node.dataset.id));
      node.addEventListener('mouseenter', () => highlightLayer(node.dataset.id));
      node.addEventListener('mouseleave', clearLayer);
    });
  }

  function highlightLayer(id) {
    const root = $('#layermap');
    const c = COMPONENTS[id];
    const deps = (c.dependsOn || []).filter(d => COMPONENTS[d]);
    const srcEl = root.querySelector(`.node[data-id="${id}"]`);
    const edges = [];
    const lit = new Set([id]);
    deps.forEach(d => {
      const tEl = root.querySelector(`.node[data-id="${d}"]`);
      if (tEl) { edges.push({ a: srcEl, b: tEl, kind: '' }); lit.add(d); }
    });
    $$('.node', root).forEach(n => n.setAttribute('data-dim', String(!lit.has(n.dataset.id))));
    layerWires.draw(edges);
  }
  function clearLayer() {
    const root = $('#layermap');
    $$('.node', root).forEach(n => n.removeAttribute('data-dim'));
    layerWires.clear();
  }

  /* ---------------------------------------------------------
     DEPENDENCY MAP
     --------------------------------------------------------- */
  const DEP_TIERS = [
    { label: 'Entry · Composition Root',
      nodes: [
        { id: 'congine_guard', cls: 'entry', label: '@congine_guard', kind: 'AOP entry · L5' },
        { id: 'ServiceContainer', cls: 'root', label: 'ServiceContainer', kind: 'composition root · L5' },
      ] },
    { label: 'Layer 4 · Concrete implementations  +  Layer 2 · Validator',
      spread: true,
      nodes: [
        { id: 'LFUCache', kind: 'L4' },
        { id: 'HttpContractRepository', kind: 'L4' },
        { id: 'QueueEventBus', kind: 'L4' },
        { id: 'StructuredLogger', kind: 'L4' },
        { id: 'ValidationTimer', kind: 'L4' },
        { id: 'LocalValidator', kind: 'L2' },
      ] },
    { label: 'Layer 1 · Protocol seam (structural)',
      spread: true,
      nodes: [
        { id: 'ISchemaStorage', kind: 'L1' },
        { id: 'IContractRepository', kind: 'L1' },
        { id: 'IEventBus', kind: 'L1' },
        { id: 'ILogger', kind: 'L1' },
        { id: 'IValidator', kind: 'L1' },
      ] },
    { label: 'Layer 3 · Consumer',
      nodes: [
        { id: 'ValidateContractUseCase', kind: 'orchestrator · L3' },
      ] },
  ];

  // from → to edges (ids match dep nodes)
  const DEP_EDGES = [
    // guard
    { from: 'congine_guard', to: 'ServiceContainer', kind: '', dashed: true },   // resolves
    { from: 'congine_guard', to: 'ValidateContractUseCase', kind: 'hot' },       // calls execute()
    // container instantiates concretes
    { from: 'ServiceContainer', to: 'LFUCache' },
    { from: 'ServiceContainer', to: 'HttpContractRepository' },
    { from: 'ServiceContainer', to: 'QueueEventBus' },
    { from: 'ServiceContainer', to: 'StructuredLogger' },
    { from: 'ServiceContainer', to: 'ValidationTimer' },
    { from: 'ServiceContainer', to: 'LocalValidator' },
    { from: 'ServiceContainer', to: 'ValidateContractUseCase' },                 // constructs
    // concretes satisfy protocols
    { from: 'LFUCache', to: 'ISchemaStorage', dashed: true },
    { from: 'HttpContractRepository', to: 'IContractRepository', dashed: true },
    { from: 'QueueEventBus', to: 'IEventBus', dashed: true },
    { from: 'StructuredLogger', to: 'ILogger', dashed: true },
    { from: 'LocalValidator', to: 'IValidator', dashed: true },
    // protocols injected into use case
    { from: 'ISchemaStorage', to: 'ValidateContractUseCase' },
    { from: 'IEventBus', to: 'ValidateContractUseCase' },
    { from: 'ILogger', to: 'ValidateContractUseCase' },
    { from: 'IValidator', to: 'ValidateContractUseCase' },
    // timer injected directly (no protocol)
    { from: 'ValidationTimer', to: 'ValidateContractUseCase' },
  ];

  let depWires = null;
  function buildDepMap() {
    const root = $('#depmap');
    root.innerHTML = DEP_TIERS.map(t => `
      <div class="dep-tier">
        <div class="dt-label">${t.label}</div>
        <div class="dep-row ${t.spread ? 'spread' : ''}">
          ${t.nodes.map(n => {
            const c = COMPONENTS[n.id];
            const acc = c ? HUE[c.layer] : 'var(--signal)';
            return `<div class="dep-node ${n.cls || ''}" data-id="${n.id}" style="--accent:${acc}">
              <div class="dn-name">${n.label || (c ? c.name : n.id)}</div>
              <div class="dn-kind">${n.kind}</div>
            </div>`;
          }).join('')}
        </div>
      </div>`).join('');
    depWires = window.Wires(root);

    $$('.dep-node', root).forEach(node => {
      node.addEventListener('click', () => { if (COMPONENTS[node.dataset.id]) openDrawer(node.dataset.id); });
      node.addEventListener('mouseenter', () => drawDep(node.dataset.id));
      node.addEventListener('mouseleave', () => drawDep(null));
    });
    drawDep(null);
  }

  function elFor(root, id) { return root.querySelector(`.dep-node[data-id="${id}"]`); }

  function drawDep(hoverId) {
    const root = $('#depmap');
    if (!depWires) return;
    const edges = [];
    if (!hoverId) {
      DEP_EDGES.forEach(e => edges.push({
        a: elFor(root, e.from), b: elFor(root, e.to), kind: e.kind || '', dashed: e.dashed,
      }));
      depWires.svg.style.opacity = '0.4';
      $$('.dep-node', root).forEach(n => { n.removeAttribute('data-dim'); n.removeAttribute('data-lit'); });
    } else {
      const lit = new Set([hoverId]);
      DEP_EDGES.forEach(e => {
        const touch = e.from === hoverId || e.to === hoverId;
        if (touch) { lit.add(e.from); lit.add(e.to); }
        edges.push({
          a: elFor(root, e.from), b: elFor(root, e.to),
          kind: touch ? (e.kind || '') : 'dim', dashed: e.dashed,
        });
      });
      depWires.svg.style.opacity = '1';
      $$('.dep-node', root).forEach(n => {
        const on = lit.has(n.dataset.id);
        n.setAttribute('data-dim', String(!on));
        if (n.dataset.id === hoverId) n.setAttribute('data-lit', 'true'); else n.removeAttribute('data-lit');
      });
    }
    depWires.draw(edges);
  }

  /* ---------------------------------------------------------
     TABS
     --------------------------------------------------------- */
  const SHEETS = ['overview','layermap','depmap','flowA','flowB','lfu','adr'];
  let current = 'overview';
  const redraws = {
    layermap: () => { if (layerWires) layerWires.clear(); },
    depmap:   () => drawDep(null),
    flowA:    () => window.FLOWS && window.FLOWS.redraw && window.FLOWS.redraw('flowA'),
    flowB:    () => window.FLOWS && window.FLOWS.redraw && window.FLOWS.redraw('flowB'),
  };

  function activate(view) {
    current = view;
    $$('.tab').forEach(t => t.setAttribute('aria-selected', String(t.dataset.view === view)));
    $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + view));
    const idx = SHEETS.indexOf(view);
    $('#tb-sheet').textContent = String(idx).padStart(2, '0') + ' / 06';
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
    requestAnimationFrame(() => { if (redraws[view]) redraws[view](); });
  }
  $$('.tab').forEach(t => t.addEventListener('click', () => activate(t.dataset.view)));

  /* resize → redraw active diagram */
  let rt;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => {
      if (current === 'depmap') drawDep(null);
      if (current === 'layermap' && layerWires) layerWires.clear();
      if (window.FLOWS && window.FLOWS.redraw) window.FLOWS.redraw(current);
    }, 160);
  });

  /* ---------------------------------------------------------
     INIT
     --------------------------------------------------------- */
  buildLadder();
  buildLayerMap();
  buildDepMap();
  if (window.FLOWS && window.FLOWS.build) window.FLOWS.build();

  window.CONGINE_APP = { openDrawer, activate };
})();
