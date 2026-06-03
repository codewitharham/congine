/* ============================================================
   CONGINE Phase 0 — SVG connector engine
   Orthogonal routing between positioned DOM nodes.
   ============================================================ */
(function () {
  const SVGNS = 'http://www.w3.org/2000/svg';

  function el(name, attrs) {
    const n = document.createElementNS(SVGNS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  /* relative rect of `node` inside `container` coordinate space */
  function relRect(node, container) {
    const r = node.getBoundingClientRect();
    const c = container.getBoundingClientRect();
    return {
      left: r.left - c.left,
      top: r.top - c.top,
      right: r.right - c.left,
      bottom: r.bottom - c.top,
      cx: r.left - c.left + r.width / 2,
      cy: r.top - c.top + r.height / 2,
      w: r.width, h: r.height,
    };
  }

  /* Build an orthogonal path string from A to B + the arrow tip geometry */
  function ortho(a, b) {
    let d, tip, ang;
    const gap = 18;
    if (b.top >= a.bottom - 6) {
      // B below A — exit bottom, enter top
      const x1 = a.cx, y1 = a.bottom;
      const x2 = b.cx, y2 = b.top;
      const my = y1 + Math.max(gap, (y2 - y1) / 2);
      d = `M ${x1} ${y1} L ${x1} ${my} L ${x2} ${my} L ${x2} ${y2}`;
      tip = { x: x2, y: y2 }; ang = 90;
    } else if (a.top >= b.bottom - 6) {
      // B above A — exit top, enter bottom
      const x1 = a.cx, y1 = a.top;
      const x2 = b.cx, y2 = b.bottom;
      const my = y1 - Math.max(gap, (y1 - y2) / 2);
      d = `M ${x1} ${y1} L ${x1} ${my} L ${x2} ${my} L ${x2} ${y2}`;
      tip = { x: x2, y: y2 }; ang = -90;
    } else {
      // same band — side to side
      const goRight = b.cx >= a.cx;
      const x1 = goRight ? a.right : a.left;
      const x2 = goRight ? b.left : b.right;
      const y1 = a.cy, y2 = b.cy;
      const mx = x1 + (x2 - x1) / 2;
      d = `M ${x1} ${y1} L ${mx} ${y1} L ${mx} ${y2} L ${x2} ${y2}`;
      tip = { x: x2, y: y2 }; ang = goRight ? 0 : 180;
    }
    return { d, tip, ang };
  }

  function arrow(tip, ang, cls) {
    const s = 5.5;
    const g = el('path', { class: cls, d: `M 0 ${-s} L ${s * 1.6} 0 L 0 ${s} Z` });
    g.setAttribute('transform', `translate(${tip.x} ${tip.y}) rotate(${ang})`);
    g.style.fill = 'currentColor';
    g.style.stroke = 'none';
    return g;
  }

  /* Public: a manager bound to a container holding an absolute SVG layer */
  function Wires(container) {
    let svg = container.querySelector(':scope > .wire-layer');
    if (!svg) {
      svg = el('svg', { class: 'wire-layer' });
      container.insertBefore(svg, container.firstChild);
    }
    if (getComputedStyle(container).position === 'static') {
      container.style.position = 'relative';
    }

    function clear() { while (svg.firstChild) svg.removeChild(svg.firstChild); }

    /* edges: [{a:Node, b:Node, kind?, dashed?}]  kind: '' | 'hot' | 'dim' */
    function draw(edges) {
      clear();
      const rc = container.getBoundingClientRect();
      svg.setAttribute('viewBox', `0 0 ${rc.width} ${rc.height}`);
      svg.setAttribute('width', rc.width);
      svg.setAttribute('height', rc.height);
      edges.forEach(e => {
        if (!e.a || !e.b) return;
        const ra = relRect(e.a, container);
        const rb = relRect(e.b, container);
        const o = ortho(ra, rb);
        const kind = e.kind || '';
        const p = el('path', { class: 'wire ' + kind, d: o.d });
        if (e.dashed) p.setAttribute('stroke-dasharray', '4 4');
        svg.appendChild(p);
        const col = kind === 'hot' ? 'var(--signal)'
                  : kind === 'dim' ? 'var(--line-hair)'
                  : 'var(--ink-2)';
        const head = arrow(o.tip, o.ang, 'wire-dot');
        head.style.color = col;
        svg.appendChild(head);
        // origin dot
        const dot = el('circle', { r: 2.4, cx: ra.cx, cy: (rb.top >= ra.bottom - 6) ? ra.bottom : (ra.top >= rb.bottom - 6 ? ra.top : ra.cy) });
        dot.style.fill = col;
        svg.appendChild(dot);
      });
    }

    return { draw, clear, svg };
  }

  window.Wires = Wires;
})();
