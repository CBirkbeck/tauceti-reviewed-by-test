/* Tau Ceti Review: the dependency map of a declaration. What it rests on is above it and what rests
   on it below, laid out by ELK's layered algorithm; rows by depth when ELK cannot load. The layout,
   the transitive reduction and the pan and zoom follow referee-site's (LeanTrustBuilders, Apache-2.0),
   with pinch added. A node's border is its kind's colour (gold when named) and its dot its review state. */
(function () {
  'use strict';
  const {FLAG} = TauData;
  const {el, kindClass, shortName, plain} = TauRender;
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
  /* A box as wide as its label in the page's sans-serif (bold at the centre), with room for the dot and
     the arrow. */
  let ruler = null;
  function widthOf(text, bold) {
    ruler ||= document.createElement('canvas').getContext('2d');
    ruler.font = `${bold ? 600 : 400} 12px ${getComputedStyle(document.documentElement).getPropertyValue('--sans')}`;
    return Math.ceil(ruler.measureText(text).width) + 58;
  }
  const rests = (n, proof) => n.m.concat(proof ? n.p.filter(x => !n.m.includes(x)) : []);
  const restOn = (e, proof) => {
    if (!e) return [];
    const ids = [...(e.builtOn || []), ...(e.facts || []), ...(e.examples || [])];
    return proof ? ids.concat((e.usedIn || []).filter(x => !ids.includes(x))) : ids;
  };
  const restOnTotal = (e, proof) => !e ? 0 :
    (e.nBuiltOn || 0) + (e.nFacts || 0) + (e.nExamples || 0) + (proof ? e.nUsedIn || 0 : 0);

  /* The graph to draw: the centre, two levels up, one level down, and the levels the reader opened, at
     any depth and either way. `o.added` learns what each opened level drew that was not drawn before. */
  async function compose(center, entry, o) {
    const want = n => o.mathlib || (n.flags & FLAG.PROJECT);
    const nodes = new Map(), more = [];
    const put = (n, role) => {
      if (nodes.has(n.id)) return false;
      nodes.set(n.id, {...n, role, key: String(n.id), label: labelOf(n)});
      return true;
    };
    put(center, 'center');
    // A level: what `owner` rests on (or what rests on it), the first `limit`; `counted` levels end in
    // a "+ N more" node, the second level up does not (its nodes open with their arrows). Returns the
    // nodes shown, and how many new things it drew, a "+ N more" among them.
    const level = async (owner, ids, role, limit, extra, counted = true) => {
      const all = (await TauData.nodes(ids)).filter(want);
      const shown = o.all.has(owner.id + role) ? all : all.slice(0, limit);
      let added = shown.filter(n => put(n, role)).length;
      const hidden = all.length - shown.length + extra;
      if (counted && hidden > 0) { more.push({owner: owner.id, role, count: hidden, open: all.length > shown.length}); added++; }
      return {shown, added};
    };
    const capExtra = n => o.mathlib ? Math.max(0, (n.nm || 0) - n.m.length) + (o.proof ? Math.max(0, (n.np || 0) - n.p.length) : 0) : 0;
    const below = async n => {
      const e = n === center ? entry : (await TauData.decl(n.name) || {}).entry;
      return [restOn(e, o.proof), Math.max(0, restOnTotal(e, o.proof) - restOn(e, o.proof).length)];
    };
    const {shown: up} = await level(center, rests(center, o.proof), 'up', LEVEL, capExtra(center));
    for (const n of up) if ((n.flags & FLAG.PROJECT) && !o.opened.has(n.id)) await level(n, rests(n, o.proof), 'up', SECOND, 0, false);
    const [down, downExtra] = await below(center);
    await level(center, down, 'down', LEVEL, downExtra);
    // Each opened level once, over and over until none is left: one opened inside another is reached
    // once its owner is drawn, whatever order they were opened in.
    const done = new Set();
    for (let again = true; again;) {
      again = false;
      for (const id of o.opened) {
        const n = nodes.get(id);
        if (done.has(id) || !n || n.role === 'center') continue;
        done.add(id);
        again = true;
        const [ids, extra] = n.role === 'up' ? [rests(n, o.proof), capExtra(n)] : await below(n);
        o.added.set(id, (await level(n, ids, n.role, LEVEL, extra)).added);
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
    list.forEach(n => { n.w = widthOf(n.label, n.role === 'center'); });
    return {nodes: list, edges: reduce(list, edges), byId: nodes};
  }

  /* Whether opening `n` would draw more: what it rests on (or what rests on it) that the map leaves out.
     Counted for what statements rest on (the node rows say how much of it is the library's); with
     proofs, a guess, which a click that finds nothing corrects. */
  function unfolds(n, byId, o) {
    if (n.role === 'up') {
      if (o.proof) return rests(n, true).some(x => !byId.has(x)) || n.nm > n.m.length || n.np > n.p.length;
      const drawn = n.m.filter(x => byId.has(x) && (o.mathlib || byId.get(x).flags & FLAG.PROJECT)).length;
      return (o.mathlib ? n.nm : n.ml) > drawn;
    }
    if (o.proof) return true;
    let drawn = 0;
    for (const x of byId.values()) if (x.m.includes(n.id)) drawn++;
    return n.nd > drawn;
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

  function markup(g, P, ai, o) {
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
      // Its arrow: ↑ or ↓ while there is more to unfold that way, − to fold what it unfolded.
      const arrow = !project || n.role === 'center' ? '' : o.opened.has(n.id) ? '−'
        : o.empty.has(n.id + n.role) || !unfolds(n, g.byId, o) ? '' : n.role === 'up' ? '↑' : '↓';
      const what = n.role === 'up' ? 'what it rests on' : 'what rests on it';
      const cls = `node ${n.role} k-${kindClass(n.kind)}${n.flags & FLAG.NAMED ? ' named' : ''}${project ? '' : ' upstream'}`;
      const tip = [n.name, n.title && plain(n.title) !== n.label ? plain(n.title) : '', n.brief].filter(Boolean).join('\n');
      // Every node but the centre is a link to its page: a click, a middle click, Enter all follow it.
      const tag = n.role === 'center' ? 'g' : 'a', href = tag === 'a' ? ` href="${esc(TauRender.URLS.decl(n.name))}"` : '';
      s += `<${tag} class="${cls}" data-name="${esc(n.name)}"${href} transform="translate(${c.x},${c.y})">` +
        `<rect width="${n.w}" height="${H}" rx="${H / 2}"/>` +
        `<circle class="dot st-${state}" cx="15" cy="${H / 2}" r="4.2"/>` +
        `<text x="27" y="19">${esc(n.label)}</text>` +
        (arrow ? `<g class="open${arrow === '−' ? ' opened' : ''}" data-open="${n.id}" tabindex="0" role="button" transform="translate(${n.w - 13},${H / 2})">` +
          `<circle r="8"/><text y="4" text-anchor="middle">${arrow}</text><title>${arrow === '−' ? 'Fold ' + what + ' again' : 'Unfold ' + what}</title></g>` : '') +
        `<title>${esc(tip)}</title></${tag}>`;
    }
    return s + '</g>';
  }

  /* Pan, zoom and pinch, set up once for a map: `scene()` is the drawing shown ({vp, size, centerAt}, or
     null). A node is a link the browser follows; `onAction` takes a click on an arrow or a "+ N more"
     (and returns true), as do Enter and space; the click that ends a drag is no click. */
  function interact(canvas, scene, onAction) {
    let tx = 0, ty = 0, sc = 1, dragged = false;
    const apply = () => { const s = scene(); if (s) s.vp.setAttribute('transform', `translate(${tx},${ty}) scale(${sc})`); };
    const fit = () => {
      const s = scene();
      if (!s) return;
      const b = canvas.getBoundingClientRect(), size = s.size, at = s.centerAt;
      const k = Math.min(b.width / size.width, b.height / size.height, 1.2);
      if (k >= 0.55 || !at) { sc = k; tx = (b.width - size.width * k) / 2; ty = (b.height - size.height * k) / 2; }
      else { sc = 0.8; tx = b.width / 2 - at.x * sc; ty = b.height / 2 - at.y * sc; }
      apply();
    };
    const zoomAt = (mx, my, f) => { f = Math.min(Math.max(sc * f, 0.2), 3) / sc; tx = mx - (mx - tx) * f; ty = my - (my - ty) * f; sc *= f; apply(); };
    canvas.addEventListener('wheel', e => {
      if (!scene()) return;
      e.preventDefault();
      const b = canvas.getBoundingClientRect();
      zoomAt(e.clientX - b.left, e.clientY - b.top, Math.exp(-e.deltaY * 0.0015));
    }, {passive: false});
    const pointers = new Map();
    let press = null, pinch = null;
    canvas.addEventListener('pointerdown', e => {
      dragged = false;
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
      if (press && press.drag) dragged = true;
      press = null;
      canvas.classList.remove('dragging');
    };
    canvas.addEventListener('pointerup', end);
    canvas.addEventListener('pointercancel', end);
    canvas.addEventListener('click', e => {
      if (dragged || onAction(e.target)) { e.preventDefault(); e.stopPropagation(); }
      dragged = false;
    }, true);
    canvas.addEventListener('keydown', e => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('[data-open], [data-more]') && onAction(e.target)) e.preventDefault();
    });
    return {fit, zoom: f => { const b = canvas.getBoundingClientRect(); zoomAt(b.width / 2, b.height / 2, f); }};
  }

  /* Esc leaves full screen, for whichever map is in it. */
  let leaveFull = null;
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && leaveFull) leaveFull(); });

  /* Draws the map of `center` (a TauData node) in `host`; `entry` is its module entry, null for a
     declaration outside the library. `opts.ai()` says whether the reader counts AI reviews; `opts.lib`
     is the library's name. */
  function draw(host, center, entry, opts) {
    const o = {proof: false, mathlib: false, opened: new Set(), all: new Set(), added: new Map(), empty: new Set()};
    const ai = (opts && opts.ai) || (() => false), lib = (opts && opts.lib) || 'the library';
    host.replaceChildren();
    const box = el('div', 'map'), tools = el('div', 'map-tools'), canvas = el('div', 'map-canvas'), note = el('div', 'map-note');
    note.setAttribute('role', 'status');
    const toggle = (text, key, title) => {
      const b = el('button', 'btn small', text);
      b.type = 'button'; b.title = title; b.setAttribute('aria-pressed', String(o[key]));
      // What an arrow found nothing behind may be there now: Mathlib's declarations, or proofs.
      b.addEventListener('click', () => { o[key] = !o[key]; o.empty.clear(); b.setAttribute('aria-pressed', String(o[key])); render(); });
      return b;
    };
    const action = (text, fn, title) => { const b = el('button', 'btn small', text); b.type = 'button'; b.title = title; b.addEventListener('click', fn); return b; };
    const full = action('Full screen', () => setFull(!box.classList.contains('full')), 'Fill the window');
    function setFull(on) {
      box.classList.toggle('full', on);
      full.textContent = on ? '✕ Leave full screen' : 'Full screen';
      full.title = on ? 'Back to the page (Esc)' : 'Fill the window';
      full.classList.toggle('primary', on);
      leaveFull = on ? () => setFull(false) : null;
      requestAnimationFrame(() => view.fit());
    }
    tools.append(toggle('Proof uses', 'proof', 'Add the results its proof uses (dashed), and the proofs that use it'),
                 toggle('Mathlib', 'mathlib', "Show the declarations from Mathlib and Lean's core it rests on"),
                 action('Fit', () => view.fit(), 'Fit the map to the frame'), full,
                 el('span', 'hint', 'Click a box to open it · ↑ ↓ unfold a level, − folds it · drag to move · scroll or pinch to zoom'));
    box.append(tools, canvas, note);
    host.append(box);
    let gen = 0, g = null, scene = null, opening = null, hush = 0;
    const say = text => {
      note.textContent = text;
      note.classList.add('on');
      clearTimeout(hush);
      hush = setTimeout(() => note.classList.remove('on'), 6000);
    };
    const view = interact(canvas, () => scene, target => {
      const open = target.closest('[data-open]'), moreNode = target.closest('[data-more]');
      if (open) {
        const id = +open.dataset.open;
        if (o.opened.delete(id)) { o.all.delete(id + 'up'); o.all.delete(id + 'down'); opening = null; }
        else { o.opened.add(id); opening = id; }
        render();
        return true;
      }
      if (moreNode) { const m = g && g.nodes.find(n => n.key === moreNode.dataset.more); if (m && m.open) { o.all.add(m.owner + m.dir); render(); } return true; }
      return false;
    });
    async function render() {
      const mine = ++gen, tried = opening;
      opening = null;
      if (scene) canvas.classList.add('busy');
      else canvas.replaceChildren(el('p', 'map-wait', 'Drawing the map…'));
      const next = await compose(center, entry, o);
      // An arrow with nothing behind it says so, and goes.
      const n = tried != null && next.byId.get(tried);
      if (n && !o.added.get(tried) && o.opened.delete(tried)) {
        o.empty.add(tried + n.role);
        say(n.role === 'down' ? `Nothing else in ${lib} rests on “${n.label}”.`
          : o.mathlib || o.proof ? `Everything “${n.label}” rests on is drawn already.`
          : `Everything else “${n.label}” rests on is in Mathlib or Lean: turn on Mathlib to see it.`);
      }
      let P;
      try { P = await placeWithElk(next); } catch (e) { P = placeInRows(next); }
      if (mine !== gen || !canvas.isConnected) return;
      g = next;
      canvas.classList.remove('busy');
      if (g.nodes.length <= 1) {
        scene = null;
        canvas.style.setProperty('--h', 'auto');
        canvas.replaceChildren(el('p', 'map-wait', o.mathlib ? 'It rests on nothing drawn here, and nothing here rests on it.'
          : `Within ${lib} it rests on nothing, and nothing rests on it: turn on Mathlib to see what it is built from.`));
        return;
      }
      // As tall as the drawing needs, at the scale that fits its width.
      const wide = canvas.getBoundingClientRect().width || 700;
      canvas.style.setProperty('--h', Math.round(Math.max(240, Math.min(560, P.height * Math.min(1.2, wide / P.width) + 30))) + 'px');
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.innerHTML = markup(g, P, ai(), o); // names escaped; titles escaped; everything else ours
      canvas.replaceChildren(svg);
      const at = P.coords.get(String(center.id));
      scene = {vp: svg.querySelector('.vp'), size: P, centerAt: at && {x: at.x + labelOf(center).length * 3.2 + 25, y: at.y + H / 2}};
      svg.querySelectorAll('.node[data-name]').forEach(n => {
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
