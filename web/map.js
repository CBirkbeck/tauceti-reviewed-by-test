/* Tau Ceti Review: the dependency map of a declaration. What it rests on is above it and what rests
   on it below, laid out by ELK's layered algorithm; rows by depth when ELK cannot load. The layout,
   the transitive reduction and the pan and zoom follow referee-site's (LeanTrustBuilders, Apache-2.0),
   with pinch added. Each node is the Atlas's planet, ringed by its review state. */
(function () {
  'use strict';
  const {FLAG} = TauData;
  const {el, glyphMarkup, shortName, plain} = TauRender;
  const LEVEL = 12, SECOND = 4, H = 30;
  const ELK_SRC = 'vendor/elk-0.9.3.bundled.js';
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  let elkEngine = null;

  function loadElk() {
    if (!elkEngine) elkEngine = new Promise((ok, fail) => {
      if (window.ELK) { ok(new window.ELK()); return; }
      const s = document.createElement('script');
      s.src = ELK_SRC;
      s.onload = () => window.ELK ? ok(new window.ELK()) : fail(new Error('ELK did not load'));
      s.onerror = () => fail(new Error('ELK could not be loaded'));
      document.head.appendChild(s);
    }).catch(e => { elkEngine = null; throw e; });
    return elkEngine;
  }

  const labelOf = n => {
    const t = (n.flags & FLAG.NAMED) && n.title ? plain(n.title) : shortName(n.name);
    return t.length > 34 ? t.slice(0, 33) + '…' : t;
  };
  const widthOf = text => Math.round(Math.min(34, text.length) * 6.4 + 50);
  const rests = (n, proof) => n.m.concat(proof ? n.p.filter(x => !n.m.includes(x)) : []);
  const restOn = (e, proof) => {
    if (!e) return [];
    const ids = [...(e.builtOn || []), ...(e.facts || []), ...(e.examples || [])];
    return proof ? ids.concat((e.usedIn || []).filter(x => !ids.includes(x))) : ids;
  };
  const restOnTotal = (e, proof) => !e ? 0 :
    (e.nBuiltOn || 0) + (e.nFacts || 0) + (e.nExamples || 0) + (proof ? e.nUsedIn || 0 : 0);

  /* The graph to draw: the centre, two levels up, one level down, and the levels the reader opened. */
  async function compose(center, entry, o) {
    const want = n => o.mathlib || (n.flags & FLAG.PROJECT);
    const nodes = new Map(), more = [];
    const put = (n, role) => { if (!nodes.has(n.id)) nodes.set(n.id, {...n, role, key: String(n.id), label: labelOf(n)}); };
    put(center, 'center');
    // A level: what `owner` rests on (or what rests on it), the first `limit`; `counted` levels end in
    // a "+ N more" node, the second level up does not (its nodes open with their arrows).
    const level = async (owner, ids, role, limit, extra, counted = true) => {
      const all = (await TauData.nodes(ids)).filter(want);
      const shown = o.all.has(owner.id + role) ? all : all.slice(0, limit);
      shown.forEach(n => put(n, role));
      const hidden = all.length - shown.length + extra;
      if (counted && hidden > 0) more.push({owner: owner.id, role, count: hidden, open: all.length > shown.length});
      return shown;
    };
    const capExtra = n => o.mathlib ? Math.max(0, (n.nm || 0) - n.m.length) + (o.proof ? Math.max(0, (n.np || 0) - n.p.length) : 0) : 0;
    const up = await level(center, rests(center, o.proof), 'up', LEVEL, capExtra(center));
    for (const n of up) if (n.flags & FLAG.PROJECT) await level(n, rests(n, o.proof), 'up', o.opened.has(n.id) ? LEVEL : SECOND, 0, o.opened.has(n.id));
    await level(center, restOn(entry, o.proof), 'down', LEVEL, Math.max(0, restOnTotal(entry, o.proof) - restOn(entry, o.proof).length));
    for (const id of o.opened) {
      const n = nodes.get(id);
      if (n && n.role === 'down') {
        const d = await TauData.decl(n.name);
        await level(n, restOn(d && d.entry, o.proof), 'down', LEVEL, 0, true);
      }
    }
    // Every edge between nodes drawn, from what each rests on (so shared dependencies join up).
    const edges = [];
    for (const a of nodes.values()) {
      for (const b of a.m) if (nodes.has(b) && b !== a.id) edges.push({a: a.id, b, proof: false});
      if (o.proof) for (const b of a.p) if (nodes.has(b) && b !== a.id && !a.m.includes(b)) edges.push({a: a.id, b, proof: true});
    }
    for (const n of nodes.values()) {
      if (n.role === 'down' && !edges.some(e => e.a === n.id)) edges.push({a: n.id, b: center.id, proof: o.proof});
    }
    const list = [...nodes.values()];
    for (const m of more) {
      const key = `more-${m.owner}-${m.role}`, text = `+ ${m.count.toLocaleString('en')} more`;
      list.push({key, id: key, role: 'more', label: text, owner: m.owner, dir: m.role, open: m.open, flags: 0});
      edges.push(m.role === 'up' ? {a: m.owner, b: key, proof: false} : {a: key, b: m.owner, proof: false});
    }
    list.forEach(n => { n.w = widthOf(n.label); });
    return {nodes: list, edges: reduce(list, edges)};
  }

  /* The edges no longer path implies (referee-site's transitiveReduction). */
  function reduce(nodes, edges) {
    const adj = new Map(nodes.map(n => [String(n.key), new Set()]));
    const proof = new Map();
    for (const e of edges) {
      const a = String(e.a), b = String(e.b);
      if (adj.has(a) && adj.has(b) && a !== b) { adj.get(a).add(b); proof.set(a + '>' + b, e.proof && !proof.get(a + '>' + b)); }
    }
    const reach = (a, skip) => {
      const seen = new Set(), stack = [...adj.get(a)].filter(x => x !== skip);
      while (stack.length) { const x = stack.pop(); if (seen.has(x)) continue; seen.add(x); stack.push(...adj.get(x)); }
      return seen;
    };
    const out = [];
    for (const [a, bs] of adj) for (const b of bs) if (!reach(a, b).has(b)) out.push({a, b, proof: proof.get(a + '>' + b)});
    return out;
  }

  /* Where things go: ELK's layered layout, top-down, dependencies above. */
  function sectionPath(sec, dx, dy) {
    const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map(p => `${(p.x + dx).toFixed(1)},${(p.y + dy).toFixed(1)}`);
    let d = `M${pts[0]}`;
    if ((pts.length - 1) % 3 === 0) { for (let i = 1; i + 2 < pts.length; i += 3) d += `C${pts[i]} ${pts[i + 1]} ${pts[i + 2]}`; return d; }
    return d + 'L' + pts.slice(1).join('L');
  }
  async function placeWithElk(g) {
    const elk = await loadElk();
    const res = await elk.layout({id: 'root',
      layoutOptions: {'elk.algorithm': 'layered', 'elk.direction': 'DOWN', 'elk.edgeRouting': 'SPLINES',
        'elk.spacing.nodeNode': '16', 'elk.layered.spacing.nodeNodeBetweenLayers': '44',
        'elk.layered.spacing.edgeNodeBetweenLayers': '14', 'elk.spacing.edgeNode': '10', 'elk.spacing.edgeEdge': '6',
        'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF', 'elk.padding': '[top=20,left=20,bottom=20,right=20]'},
      children: g.nodes.map(n => ({id: 'n' + n.key, width: n.w, height: H})),
      edges: g.edges.map((e, i) => ({id: 'e' + i, sources: ['n' + e.b], targets: ['n' + e.a]}))});
    const coords = new Map((res.children || []).map(c => [c.id.slice(1), {x: c.x, y: c.y}]));
    const byEdge = new Map((res.edges || []).map(e => [e.id, e]));
    const paths = g.edges.map((e, i) => { const s = byEdge.get('e' + i)?.sections?.[0]; return s ? sectionPath(s, 0, 0) : ''; });
    return {coords, paths, width: res.width, height: res.height};
  }
  /* Without ELK: rows by longest path, each centred, one curve per edge. */
  function placeInRows(g) {
    const deps = new Map(g.nodes.map(n => [n.key, []]));
    g.edges.forEach(e => deps.get(e.a)?.push(e.b));
    const depth = new Map(), visiting = new Set();
    const d = k => {
      if (depth.has(k)) return depth.get(k);
      if (visiting.has(k)) return 0;
      visiting.add(k);
      let r = 0;
      for (const t of deps.get(k) || []) r = Math.max(r, d(t) + 1);
      visiting.delete(k); depth.set(k, r); return r;
    };
    const rows = [];
    g.nodes.forEach(n => (rows[d(n.key)] ||= []).push(n));
    rows.reverse();
    const coords = new Map(), GAP = 16, ROW = H + 44;
    let width = 0;
    rows.forEach(r => { width = Math.max(width, (r || []).reduce((s, n) => s + n.w + GAP, -GAP)); });
    rows.forEach((r, k) => {
      let x = (width - (r || []).reduce((s, n) => s + n.w + GAP, -GAP)) / 2 + 20;
      (r || []).forEach(n => { coords.set(n.key, {x, y: 20 + k * ROW}); x += n.w + GAP; });
    });
    const byKey = new Map(g.nodes.map(n => [n.key, n]));
    const paths = g.edges.map(e => {
      const p = coords.get(e.b), q = coords.get(e.a);
      if (!p || !q) return '';
      const x1 = p.x + byKey.get(e.b).w / 2, y1 = p.y + H, x2 = q.x + byKey.get(e.a).w / 2, y2 = q.y, m = (y1 + y2) / 2;
      return `M${x1},${y1} C${x1},${m} ${x2},${m} ${x2},${y2}`;
    });
    return {coords, paths, width: width + 40, height: rows.length * ROW + 40};
  }

  function markup(g, P, ai) {
    let s = '<g class="vp">';
    g.edges.forEach((e, i) => {
      if (P.paths[i]) s += `<path class="edge${e.proof ? ' proof' : ''}" data-a="${esc(e.a)}" data-b="${esc(e.b)}" d="${P.paths[i]}"/>`;
    });
    for (const n of g.nodes) {
      const c = P.coords.get(n.key);
      if (!c) continue;
      if (n.role === 'more') {
        s += `<g class="node more" data-more="${esc(n.key)}" tabindex="0" role="button" transform="translate(${c.x},${c.y})">` +
          `<rect width="${n.w}" height="${H}" rx="${H / 2}"/><text x="${n.w / 2}" y="19" text-anchor="middle">${esc(n.label)}</text>` +
          `<title>${n.open ? 'Show them' : 'More than the map keeps: see the lists below'}</title></g>`;
        continue;
      }
      const project = !!(n.flags & FLAG.PROJECT), state = n.state[ai ? 1 : 0];
      const canOpen = project && n.role !== 'center';
      s += `<g class="node ${n.role}${project ? '' : ' upstream'}" data-name="${esc(n.name)}" tabindex="0" role="link" transform="translate(${c.x},${c.y})">` +
        `<rect width="${n.w}" height="${H}" rx="${H / 2}"/>` +
        `<g transform="translate(16,${H / 2})">${glyphMarkup(n.kind, state, {r: 4.6, named: !!(n.flags & FLAG.NAMED), upstream: !project})}</g>` +
        `<text x="32" y="19">${esc(n.label)}</text>` +
        (canOpen ? `<g class="open" data-open="${n.id}" transform="translate(${n.w - 13},${H / 2})"><circle r="8"/><text y="4" text-anchor="middle">${n.role === 'up' ? '↑' : '↓'}</text><title>Show what ${n.role === 'up' ? 'it rests on' : 'rests on it'}</title></g>` : '') +
        `<title>${esc(n.name + (n.title && plain(n.title) !== n.label ? ' — ' + plain(n.title) : ''))}</title></g>`;
    }
    return s + '</g>';
  }

  /* Pan, zoom and pinch; a press that does not move is a click. */
  function interact(canvas, svg, vp, size, centerAt, onClick) {
    let tx = 0, ty = 0, sc = 1;
    const apply = () => vp.setAttribute('transform', `translate(${tx},${ty}) scale(${sc})`);
    const fit = () => {
      const b = canvas.getBoundingClientRect();
      const s = Math.min(b.width / size.width, b.height / size.height, 1.2);
      if (s >= 0.55 || !centerAt) { sc = s; tx = (b.width - size.width * s) / 2; ty = (b.height - size.height * s) / 2; }
      else { sc = 0.8; tx = b.width / 2 - centerAt.x * sc; ty = b.height / 2 - centerAt.y * sc; }
      apply();
    };
    const zoomAt = (mx, my, f) => { f = Math.min(Math.max(sc * f, 0.2), 3) / sc; tx = mx - (mx - tx) * f; ty = my - (my - ty) * f; sc *= f; apply(); };
    canvas.addEventListener('wheel', e => {
      e.preventDefault();
      const b = canvas.getBoundingClientRect();
      zoomAt(e.clientX - b.left, e.clientY - b.top, Math.exp(-e.deltaY * 0.0015));
    }, {passive: false});
    const pointers = new Map();
    let press = null, pinch = null;
    canvas.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
      if (pointers.size === 2) {
        const [p, q] = [...pointers.values()];
        pinch = {d: Math.hypot(p.x - q.x, p.y - q.y), sc};
        press = null;
      } else press = {x: e.clientX, y: e.clientY, tx, ty, target: e.target, drag: false, id: e.pointerId};
    });
    canvas.addEventListener('pointermove', e => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
      if (pinch && pointers.size === 2) {
        const [p, q] = [...pointers.values()], b = canvas.getBoundingClientRect();
        zoomAt((p.x + q.x) / 2 - b.left, (p.y + q.y) / 2 - b.top, pinch.sc * Math.hypot(p.x - q.x, p.y - q.y) / pinch.d / sc);
        return;
      }
      if (!press) return;
      if (!press.drag && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 4) {
        press.drag = true; canvas.setPointerCapture(press.id); canvas.classList.add('dragging');
      }
      if (press.drag) { tx = press.tx + e.clientX - press.x; ty = press.ty + e.clientY - press.y; apply(); }
    });
    const end = e => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      const p = press;
      press = null;
      canvas.classList.remove('dragging');
      if (p && !p.drag && e.type === 'pointerup') onClick(p.target);
    };
    canvas.addEventListener('pointerup', end);
    canvas.addEventListener('pointercancel', end);
    return {fit, zoom: f => { const b = canvas.getBoundingClientRect(); zoomAt(b.width / 2, b.height / 2, f); }};
  }

  /* Draws the map of `center` (a TauData node) in `host`; `entry` is its module entry, null for a
     declaration outside the library. `ai()` says whether the reader counts AI reviews. */
  function draw(host, center, entry, opts) {
    const o = {proof: false, mathlib: false, opened: new Set(), all: new Set()};
    const ai = (opts && opts.ai) || (() => false);
    host.replaceChildren();
    const box = el('div', 'map'), tools = el('div', 'map-tools'), canvas = el('div', 'map-canvas');
    const toggle = (text, key, title) => {
      const b = el('button', 'btn small', text);
      b.type = 'button'; b.title = title; b.setAttribute('aria-pressed', String(o[key]));
      b.addEventListener('click', () => { o[key] = !o[key]; b.setAttribute('aria-pressed', String(o[key])); render(); });
      return b;
    };
    const action = (text, fn, title) => { const b = el('button', 'btn small', text); b.type = 'button'; b.title = title; b.addEventListener('click', fn); return b; };
    let view = null;
    tools.append(toggle('Proof uses', 'proof', 'Add the results its proof uses (dashed), and the proofs that use it'),
                 toggle('Mathlib', 'mathlib', "Show the declarations from Mathlib and Lean's core it rests on"),
                 action('Fit', () => view && view.fit(), 'Fit the map to the frame'),
                 action('Full screen', () => { box.classList.toggle('full'); requestAnimationFrame(() => view && view.fit()); }, 'Fill the window; again to return'),
                 el('span', 'hint', 'Click to open · ↑ ↓ to unfold · drag to move · scroll or pinch to zoom'));
    box.append(tools, canvas);
    host.append(box);
    let gen = 0;
    async function render() {
      const mine = ++gen;
      canvas.replaceChildren(el('p', 'map-wait', 'Drawing the map…'));
      const g = await compose(center, entry, o);
      let P;
      try { P = await placeWithElk(g); } catch (e) { P = placeInRows(g); }
      if (mine !== gen || !canvas.isConnected) return;
      if (g.nodes.length <= 1) {
        canvas.style.height = '';
        canvas.replaceChildren(el('p', 'map-wait', o.mathlib ? 'It rests on nothing drawn here, and nothing here rests on it.'
          : 'Within Tau Ceti it rests on nothing, and nothing rests on it: turn on Mathlib to see what it is built from.'));
        return;
      }
      // As tall as the drawing needs, at the scale that fits its width.
      const wide = canvas.getBoundingClientRect().width || 700;
      canvas.style.height = Math.round(Math.max(240, Math.min(560, P.height * Math.min(1.2, wide / P.width) + 30))) + 'px';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.innerHTML = markup(g, P, ai()); // names escaped; titles escaped; everything else ours
      canvas.replaceChildren(svg);
      const vp = svg.querySelector('.vp'), at = P.coords.get(String(center.id));
      view = interact(canvas, svg, vp, P, at && {x: at.x + labelOf(center).length * 3.2 + 25, y: at.y + H / 2}, target => {
        const open = target.closest('[data-open]'), moreNode = target.closest('[data-more]'), node = target.closest('[data-name]');
        if (open) { o.opened.add(+open.dataset.open); render(); }
        else if (moreNode) { const m = g.nodes.find(n => n.key === moreNode.dataset.more); if (m && m.open) { o.all.add(m.owner + m.dir); render(); } }
        else if (node && node.dataset.name !== center.name) location.hash = TauRender.URLS.decl(node.dataset.name);
      });
      svg.querySelectorAll('.node[data-name]').forEach(n => {
        n.addEventListener('keydown', e => { if (e.key === 'Enter') location.hash = TauRender.URLS.decl(n.dataset.name); });
        n.addEventListener('mouseenter', () => svg.querySelectorAll('.edge').forEach(p => {
          const k = n.dataset.name, keyOf = g.nodes.find(x => x.name === k)?.key;
          p.classList.toggle('hot', p.dataset.a === keyOf || p.dataset.b === keyOf);
        }));
        n.addEventListener('mouseleave', () => svg.querySelectorAll('.edge.hot').forEach(p => p.classList.remove('hot')));
      });
      requestAnimationFrame(() => view.fit());
    }
    render();
    return {redraw: render};
  }

  window.TauMap = Object.freeze({draw});
})();
