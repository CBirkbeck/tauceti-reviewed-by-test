/* Tau Ceti Review: the pages: a hash router (#/…) and one function per page. Everything shown
   comes from TauData (what the build wrote), laid out with TauRender and TauMap. */
(function () {
  'use strict';
  const {el, link, ext, md, mdInline, kindClass, kindPill, KIND_WORD, stateBadge, STATE_TEXT, URLS, FORMS, issueBody, ANSWERS, SUGGEST,
         SUGGEST_TEST, questionWord, date, plural, who, shortName, plain} = TauRender;
  const {FLAG, STATES} = TauData;
  const $ = id => document.getElementById(id);
  const main = $('main');
  let generation = 0, ready = false, current = '';
  let ai = false;
  try { ai = localStorage.getItem('tauceti-review:ai') === '1'; } catch (e) { /* no storage: the default */ }
  const pick = pair => pair[ai ? 1 : 0];
  const stateOf = n => pick(n.state);
  const rowState = r => STATES[pick(r.s)] || 'unreviewed';
  const count = n => Number(n).toLocaleString('en');

  /* --- addresses ---------------------------------------------------------------------------------- */
  function parse(hash) {
    const h = (hash || '').replace(/^#/, '');
    if (h && !h.startsWith('/') && h.includes('=')) {          // the old site's addresses: #d=…&m=…&q=…
      const p = new URLSearchParams(h);
      if (p.get('d')) return ['decl', p.get('d')];
      if (p.get('m')) return ['module', p.get('m')];
      if (p.get('q')) return ['search', p.get('q')];
      if (p.get('area')) return ['area', p.get('area')];
      return ['home'];
    }
    const [head, ...rest] = h.replace(/^\//, '').split('/');
    const arg = decodeURIComponent(rest.join('/'));
    return ({'': ['home'], named: ['named'], reviewed: ['reviewed'], d: ['decl', arg], m: ['module', arg], area: ['area', arg],
             search: ['search', arg], browse: ['browse'], activity: ['activity'], help: ['help']})[head] || ['missing', h];
  }
  const address = r => ({home: '#/', named: '#/named', reviewed: '#/reviewed', decl: '#/d/', module: '#/m/', area: '#/area/',
                         search: '#/search/', browse: '#/browse', activity: '#/activity', help: '#/help'})[r[0]] +
                       (r[1] != null ? encodeURIComponent(r[1]) : '');

  /* --- frame ---------------------------------------------------------------------------------------- */
  function show(...nodes) { main.replaceChildren(...nodes.filter(Boolean)); window.scrollTo(0, 0); }
  function setNav(which) { document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === which)); }
  function crumbs(trail) {
    const c = el('div', 'crumbs');
    trail.forEach(([text, href], i) => {
      if (i) c.append(el('span', 'sep', '›'));
      c.append(href ? link(href, text) : el('span', null, text));
    });
    return c;
  }
  /* A section: its title, a count beside it, and what it holds. */
  function section(title, n, ...body) {
    const s = el('section', 'section'), h = el('h2', null, title);
    if (n != null && n !== '') h.append(el('span', 'count', typeof n === 'number' ? count(n) : n));
    s.append(h, ...body.filter(Boolean));
    return s;
  }
  const hint = text => el('p', 'hint', text);
  const areaOf = module => { const p = module.split('.'); return p.length > 1 ? p[1] : p[0]; };
  async function moduleTrail(module) {
    const meta = await TauData.meta();
    const tail = module.split('.').slice(1).join('.') || module, area = areaOf(module);
    return [[meta.library.name, '#/browse'], [area, '#/area/' + encodeURIComponent(area)],
            ...(tail !== area ? [[tail, '#/m/' + encodeURIComponent(module)]] : [])];
  }
  /* Whether AI agents' reviews count: kept for the reader, and every page redrawn when it changes. */
  function aiSwitch() {
    const label = el('label', 'switch'), box = el('input');
    box.type = 'checkbox'; box.id = 'ai'; box.checked = ai;
    box.addEventListener('change', () => {
      ai = box.checked;
      try { localStorage.setItem('tauceti-review:ai', ai ? '1' : '0'); } catch (e) { /* not kept */ }
      route();
    });
    label.append(box, 'Count AI reviews');
    label.title = "Count AI agents' reviews as reviews; otherwise only people's count";
    return label;
  }

  /* --- lists ---------------------------------------------------------------------------------------- */
  /* A declaration in a list: what it is called or says, what it states, its Lean name, and its review
     state when it has been reviewed. Its colour is its kind's. */
  function nodeItem(n, extra) {
    const li = el('li'), a = link(URLS.decl(n.name), null, 'k-' + kindClass(n.kind)), body = el('span', 'item-body');
    a.dataset.id = n.id;
    // An untitled result is shown by what it states; an untitled notion by its name, then its type.
    if (n.title) body.append(mdInline(n.title, 'item-title', true));
    else body.append(el('span', 'item-title formula', kindClass(n.kind) === 'concept' || !n.brief ? shortName(n.name) : n.brief));
    if (n.brief && (n.title || kindClass(n.kind) === 'concept')) body.append(el('span', 'item-stmt', n.brief));
    body.append(el('span', 'item-sub', n.name));
    a.append(body);
    const st = stateOf(n), side = el('span', 'item-side');
    if (st !== 'unreviewed') side.append(stateBadge(st));
    if (extra) side.append(extra);
    if (side.childNodes.length) a.append(side);
    a.title = `${KIND_WORD[n.kind] || 'Declaration'} · ${STATE_TEXT[st]}`;
    li.append(a);
    return li;
  }
  /* A named declaration: Voyager's name and sentence, its Lean name, its state, and how much of what it
     rests on is reviewed. */
  function namedItem(r) {
    const li = el('li'), a = link(URLS.decl(r.decl), null, 'k-' + (r.what === 'result' ? 'result' : 'concept'));
    const body = el('span', 'item-body'), facts = el('span', 'item-meta');
    body.append(mdInline(r.name, 'item-title', true));
    if (r.text) body.append(mdInline(r.text, 'item-text', true));
    facts.append(el('span', 'item-sub', r.decl), stateBadge(rowState(r)));
    const [members, people, withAi, problems] = r.cov;
    if (members > 1) facts.append(coverageBar(members, people, withAi, problems));
    facts.append(el('span', null, date(r.at)));
    body.append(facts);
    a.append(body);
    li.append(a);
    return li;
  }
  /* What a named declaration rests on in the library, and how much of it is reviewed. */
  function coverageBar(members, people, withAi, problems) {
    const wrap = el('span', 'cov'), bar = el('span', 'bar');
    const part = (n, cls) => { if (n > 0) { const i = el('i', cls); i.style.width = (100 * n / members).toFixed(1) + '%'; bar.append(i); } };
    const counted = ai ? withAi : people;
    part(counted, 'b-done'); part(ai ? 0 : withAi - people, 'b-ai'); part(problems, 'b-problem');
    wrap.append(bar, `${counted}/${members}`);
    wrap.title = `Rests on ${plural(members, 'declaration')} of Tau Ceti: ${people} reviewed by people` +
      (withAi > people ? `, ${withAi - people} more by AI agents only` : '') + (problems ? `, ${problems} with an open problem` : '');
    return wrap;
  }
  function itemList(items, render, first, empty) {
    const box = el('div');
    if (!items.length) { if (empty) box.append(el('p', 'faint', empty)); return box; }
    const list = el('ul', 'list');
    const fill = k => list.replaceChildren(...items.slice(0, k).map(x => render(x)));
    fill(first);
    box.append(list);
    if (items.length > first) {
      const b = el('button', 'btn small list-more', `Show all ${count(items.length)}`);
      b.type = 'button';
      b.addEventListener('click', () => { fill(items.length); b.remove(); });
      box.append(b);
    }
    return box;
  }
  /* A ranked list of declarations: the first dozen, all the data keeps on a click, and a count of the rest. */
  async function nodeList(ids, total, empty) {
    const all = ids && ids.length ? await TauData.nodes(ids) : [];
    const box = itemList(all, n => nodeItem(n), 12, empty);
    if (ids && total > ids.length) box.append(el('p', 'faint small', `and ${plural(total - ids.length, 'more')} not listed`));
    return box;
  }

  /* --- records -------------------------------------------------------------------------------------- */
  function verdictBadge(v) {
    const words = {review: {accept: 'Correctly stated', problem: 'Not correctly stated', question: 'What could be better'}[v.verdict] || 'Review',
                   test: 'Test', challenge: 'Suggested test', named: 'Named', comment: 'Reply'};
    return el('span', 'verdict ' + (v.kind === 'review' ? v.verdict : v.kind), words[v.kind] || v.kind);
  }
  function statusNote(v) {
    return ({'stale-underneath': 'Something it rests on has changed since.', stale: 'The declaration has changed since.',
             renamed: `Written about ${v.renamedFrom}, renamed since.`, unavailable: 'Its module did not build at this commit.',
             orphaned: 'The declaration is gone.', incomparable: 'Made with another hasher: cannot be compared.'})[v.status] || '';
  }
  const STATE_WORDS = {fixed: 'Fixed', intended: 'Behaves as intended', invalid: 'Not a problem', answered: 'Answered',
                       met: 'Met', failed: 'Failed', declined: 'Declined', withdrawn: 'Withdrawn', open: 'Open'};
  function thread(v, byId) {
    const box = el('article', 'thread' + (v.applies === false || !v.inForce ? ' old' : ''));
    const head = el('div', 'thread-head');
    head.append(verdictBadge(v), who(v.by), el('span', 'faint', date(v.at)));
    if (v.url) head.append(ext(v.url, 'issue', 'faint'));
    box.append(head);
    if (v.source) box.append(el('div', 'from', `From the ${v.source.name} store`));
    const note = statusNote(v);
    if (note) box.append(el('div', 'status-note', note));
    if (v.state && !['stands', 'open'].includes(v.state)) box.append(el('div', 'state-word', STATE_WORDS[v.state] || v.state));
    else if (v.state === 'open' && v.kind !== 'review' || (v.kind === 'review' && v.verdict !== 'accept' && v.state === 'open')) box.append(el('div', 'state-word open', 'Open'));
    if (v.kind === 'named') box.append(el('div', 'named-name', v.name));
    if (v.kind === 'test' && v.test) box.append(link(URLS.decl(v.test), v.test, 'mono small'));
    if (v.category && v.category !== 'other') box.append(el('div', 'faint small', 'What is wrong: ' + v.category));
    const checked = Object.entries(v.checked || {}).filter(([, s]) => s === 'checked').map(([axis]) => axis);
    if (checked.length) { const axes = el('div', 'axes'); checked.forEach(a => axes.append(el('span', 'chip', a))); box.append(axes); }
    if (v.reference && (v.reference.text || v.reference.url)) {
      const ref = el('div', 'faint small');
      ref.append(v.kind === 'named' ? 'From: ' : 'Compared with: ');
      ref.append(v.reference.url ? ext(v.reference.url, v.reference.text || v.reference.url) : v.reference.text);
      box.append(ref);
    }
    if (v.text) box.append(md(v.text));
    if (v.statement) { const pre = el('pre', 'small-code'); pre.textContent = v.statement; box.append(pre); }
    if (v.fix) box.append(el('div', 'faint small', 'Suggested fix:'), md(v.fix));
    for (const id of v.replies || []) {
      const r = byId.get(id);
      if (!r) continue;
      const reply = el('div', 'reply'), rh = el('div', 'thread-head');
      rh.append(who(r.by), el('span', 'faint', date(r.at)));
      reply.append(rh, md(r.text));
      box.append(reply);
    }
    resolutions(box, v, who);
    if (v.actions && v.actions.length && v.url) {
      const acts = el('div', 'record-actions');
      acts.append('On its issue: ');
      v.actions.forEach((a, i) => { if (i) acts.append(' · '); acts.append(ext(v.url, '/' + a)); });
      box.append(acts);
    }
    return box;
  }

  /* A docstring after its first sentence, when it starts with the sentence a page has as its title; else all of
     it. Whitespace is compared loosely, the title being the sentence on one line. */
  function afterTitle(doc, title) {
    let i = 0, j = 0;
    const space = c => /\s/.test(c);
    while (i < doc.length && space(doc[i])) i++;
    while (j < title.length) {
      if (space(title[j])) { j++; while (i < doc.length && space(doc[i])) i++; continue; }
      if (doc[i] !== title[j]) return doc;
      i++; j++;
    }
    return doc.slice(i).replace(/^\s+/, '');
  }

  /* A docstring less its bold opening, when the opening is a sentence or a heading of its own and only says the
     title, or part of it: "**Strassmann's theorem.** Let f be …" under "Strassmann's theorem" goes on from "Let
     f be …", "**Molien's formula**: the image …" from "The image …". An opening that its sentence goes on from
     ("**X**, in Baker's form.") or that says more than the title stays. */
  function afterLead(doc, title) {
    const m = /^\s*\*\*([^*]+?)\*\*(?:(\.)|(:))?(?=\s|$)/.exec(doc);
    if (!m || !(m[2] || m[3] || /\.$/.test(m[1]))) return doc;
    const words = t => ' ' + plain(t).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/^(the|a|an) /, '') + ' ';
    const lead = words(m[1]);
    if (lead.trim().split(' ').length < 2 || !words(title).includes(lead)) return doc;
    const rest = doc.slice(m[0].length).replace(/^\s+/, '');
    return m[3] ? rest.charAt(0).toUpperCase() + rest.slice(1) : rest;
  }

  /* A signature as the docs show it: the keyword, then each name a link to its declaration (hover over
     it to see what it is), `names` the module's table of them. Positions are code points (S2), hence
     Array.from. */
  function signature(kw, text, refs, names) {
    const pre = el('pre'), cps = Array.from(text);
    if (kw) pre.append(el('span', 'kw', kw + ' '));
    let at = 0;
    [...refs].sort((a, b) => a[0] - b[0]).forEach(([a, b, k]) => {
      if (a < at || !names[k]) return;
      if (a > at) pre.append(cps.slice(at, a).join(''));
      const l = link(URLS.decl(names[k]), cps.slice(a, b).join(''), 'ref');
      l.dataset.name = names[k];
      pre.append(l);
      at = b;
    });
    if (at < cps.length) pre.append(cps.slice(at).join(''));
    pre.sig = {text, refs, names};
    markVars(pre, text);
    return pre;
  }
  /* The variables a signature binds, `(n m : ℕ)`, `{x : α}`, `⦃x : α⦄`, `[inst : C]`, each with where its type
     is in the text (code points), read from the binders before the colon that starts the conclusion. */
  const CLOSE = {'(': ')', '{': '}', '⦃': '⦄', '[': ']'}, CLOSERS = new Set(Object.values(CLOSE));
  function binders(text) {
    const cps = Array.from(text), found = [];
    for (let i = 0; i < cps.length; i++) {
      if (cps[i] === ':' && cps[i - 1] === ' ' && cps[i + 1] === ' ') break;
      if (!(cps[i] in CLOSE)) continue;
      let depth = 0, j = i;
      for (; j < cps.length; j++) {
        if (cps[j] in CLOSE) depth++;
        else if (CLOSERS.has(cps[j]) && --depth === 0) break;
      }
      let colon = -1, end = j;
      for (let k = i + 1, d = 0; k < j; k++) {
        if (cps[k] in CLOSE) d++;
        else if (CLOSERS.has(cps[k])) d--;
        else if (d === 0 && cps[k] === ':' && cps[k + 1] === '=' && colon > 0) { end = k; break; }
        else if (d === 0 && cps[k] === ':' && cps[k + 1] !== '=' && colon < 0) colon = k;
      }
      if (colon > 0) {
        const a = colon + (cps[colon + 1] === ' ' ? 2 : 1);
        cps.slice(i + 1, colon).join('').trim().split(/\s+/).filter(x => IDENT_ONLY.test(x))
          .forEach(name => found.push({name, a, b: end}));
      }
      i = j;
    }
    return found;
  }
  const IDENT = /[\p{L}_][\p{L}\p{N}_'!?\u2080-\u209c]*/gu, IDENT_ONLY = /^[\p{L}_][\p{L}\p{N}_'!?\u2080-\u209c]*$/u;
  /* Each use of a bound variable as a span to hover: it shows the variable's type and its other uses. */
  function markVars(pre, text) {
    const vars = new Map(binders(text).map(v => [v.name, v]));
    if (!vars.size) return;
    const walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT), nodes = [];
    while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('a, .kw')) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const s = node.nodeValue, frag = document.createDocumentFragment();
      let at = 0;
      for (const m of s.matchAll(IDENT)) {
        const v = vars.get(m[0]);
        if (!v) continue;
        if (m.index > at) frag.append(s.slice(at, m.index));
        const span = el('span', 'var', m[0]);
        Object.assign(span.dataset, {var: m[0], a: v.a, b: v.b});
        frag.append(span);
        at = m.index + m[0].length;
      }
      if (!at) return;
      if (at < s.length) frag.append(s.slice(at));
      node.replaceWith(frag);
    });
  }
  /* A piece of a signature, its names linked: a variable's type. */
  function sigSlice(src, a, b) {
    const text = Array.from(src.text).slice(a, b).join('').trimEnd();
    return signature(null, text, src.refs.filter(r => r[0] >= a && r[1] <= b).map(r => [r[0] - a, r[1] - a, r[2]]), src.names);
  }
  /* A definition's value, a structure's fields or an inductive type's constructors, as the source has them,
     the names of what it rests on linked: by full name, else by last component when only one fits. */
  async function valueBlock(rest, n) {
    const deps = await TauData.nodes((n.m || []).concat(n.p || []));
    const byName = new Set(deps.map(x => x.name)), byLast = new Map();
    deps.forEach(x => { const last = x.name.slice(x.name.lastIndexOf('.') + 1); byLast.set(last, byLast.has(last) && byLast.get(last) !== x.name ? null : x.name); });
    const pre = el('pre');
    let at = 0;
    for (const m of rest.matchAll(/[\p{L}_][\p{L}\p{N}_'!?\u2080-\u209c.]*/gu)) {
      const word = m[0].replace(/\.+$/, ''), dot = word.lastIndexOf('.');
      let target = byName.has(word) ? word : null, from = m.index, text = word;
      if (!target && byLast.get(word.slice(dot + 1))) { target = byLast.get(word.slice(dot + 1)); from = m.index + dot + 1; text = word.slice(dot + 1); }
      if (!target) continue;
      if (from > at) pre.append(rest.slice(at, from));
      const l = link(URLS.decl(target), text, 'ref');
      l.dataset.name = target;
      pre.append(l);
      at = from + text.length;
    }
    if (at < rest.length) pre.append(rest.slice(at));
    return pre;
  }

  /* --- pages ---------------------------------------------------------------------------------------- */
  const VIEWS = {};

  VIEWS.home = async (arg, gen) => {
    const [meta, rows] = await Promise.all([TauData.meta(), TauData.named()]);
    if (gen !== generation) return;
    const c = meta.counts, lib = meta.library.name;
    const lede = el('p', 'lede', `${lib} is a library of formalized mathematics, in Lean. Here people and AI agents review it: ` +
      'read each declaration as its documentation shows it, see what it rests on, and answer one question: is it correctly stated? ' +
      `Yes, or no and why. Nothing is written into ${lib}: an answer is kept against the declaration's hash, and says so when the declaration changes.`);
    const stats = el('div', 'stats');
    [[c.declarations, 'declarations'], [c.named, 'named by Voyager'], [c.reviewed || 0, 'reviewed', '#/reviewed'],
     [c.accepts.people, 'yes from people'], [c.accepts.ai, 'yes from AI agents'], [c.problems, 'no, still open']]
      .forEach(([n, t, href]) => {
        const s = href ? link(href, null, 'stat') : el('div', 'stat');
        s.append(el('b', null, count(n)), el('span', null, t));
        stats.append(s);
      });
    const card = (href, title, text) => { const a = link(href, null, 'card'); a.append(el('h3', null, title), el('p', null, text)); return a; };
    const cards = el('div', 'cards');
    cards.append(
      card('#/named', 'Named results', `The ${count(c.named)} theorems and definitions Voyager announced on the Lean Zulip: the ones to read first.`),
      card('#/reviewed', 'Reviewed', `The ${plural(c.reviewed || 0, 'declaration')} someone has answered for, yes or no, newest first.`),
      card('#/browse', 'Browse', `${lib} area by area: ${plural(meta.areas.length, 'area')}, ${plural(c.modules, 'file')}.`),
      card('#/activity', 'Activity', 'The latest answers, every no still open, and what to review next.'),
      card('#/help', 'How to review', 'One question, yes or no, answered on the page. No pull request.'));
    const areas = el('div', 'chips');
    meta.areas.forEach(([a, n]) => {
      const chip = link('#/area/' + encodeURIComponent(a), null, 'chip');
      chip.append(a + ' ', el('span', 'faint', count(n)));
      areas.append(chip);
    });
    setNav('');
    show(el('h1', null, `Review the mathematics in ${lib}`), lede, stats, cards,
         section('Latest named', null, itemList(rows.slice(0, 8), namedItem, 8, 'Nothing announced yet.'),
                 rows.length > 8 ? link('#/named', `All ${count(rows.length)} named results →`, 'more-link') : null),
         section('Areas', meta.areas.length, areas));
  };

  VIEWS.named = async (arg, gen) => {
    const [meta, rows] = await Promise.all([TauData.meta(), TauData.named()]);
    if (gen !== generation) return;
    const lib = meta.library.name;
    const lede = el('p', 'lede', `What Voyager has announced on the Lean Zulip as new in ${lib}: its named theorems and notable ` +
      'definitions, the declarations to read first. Open one to read it, see what it rests on, and review it.');
    const results = rows.filter(r => r.what === 'result').length;
    const by = st => rows.filter(r => rowState(r) === st).length;
    const summary = el('p', 'summary', [`${count(rows.length)} named`, plural(results, 'result'), plural(rows.length - results, 'definition'),
      `${count(by('covered') + by('disputed'))} reviewed${ai ? ', counting AI agents' : ' by people'}`,
      `${count(by('unreviewed'))} not reviewed yet`].join(' · '));
    // Filters: kind, area, state, order, words; each area a list.
    const st = {what: 'all', area: '', state: '', sort: 'new', q: ''};
    const filters = el('div', 'filters'), seg = el('div', 'seg');
    [['all', 'All'], ['result', 'Results'], ['definition', 'Definitions']].forEach(([k, t]) => {
      const b = el('button', k === st.what ? 'on' : '', t);
      b.type = 'button'; b.dataset.what = k;
      b.addEventListener('click', () => { st.what = k; seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); draw(); });
      seg.append(b);
    });
    const select = (options, key, label) => {
      const s = el('select', 'select'); s.setAttribute('aria-label', label);
      options.forEach(([v, t]) => { const o = el('option', null, t); o.value = v; s.append(o); });
      s.addEventListener('change', () => { st[key] = s.value; draw(); });
      return s;
    };
    const order = meta.areas.map(a => a[0]), place = a => (order.indexOf(a) + 1) || order.length + 1;
    const areas = [...new Set(rows.map(r => r.area))].sort((a, b) => place(a) - place(b) || a.localeCompare(b));
    const q = el('input', 'filter-input');
    q.type = 'search'; q.placeholder = 'Filter by name or words'; q.setAttribute('aria-label', 'Filter');
    let typing = null;
    q.addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(() => { st.q = q.value.toLowerCase(); draw(); }, 150); });
    filters.append(seg, select([['', 'Every area'], ...areas.map(a => [a, a])], 'area', 'Area'),
                   select([['', 'Any review state'], ['covered', 'Reviewed'], ['unreviewed', 'Not reviewed yet'],
                           ['uncounted', 'Reviewed by AI only'], ['stale', 'Reviewed on an earlier version'], ['problem', 'Answered no']], 'state', 'Review state'),
                   select([['new', 'Newest first'], ['name', 'By name'], ['imp', 'Most built upon']], 'sort', 'Order'), q, aiSwitch());
    const found = el('p', 'faint small'), groups = el('div');
    function draw() {
      let list = rows.filter(r => (st.what === 'all' || r.what === st.what) && (!st.area || r.area === st.area) &&
        (!st.state || rowState(r) === st.state || (st.state === 'problem' && rowState(r) === 'disputed')) &&
        (!st.q || (r.name + ' ' + r.decl + ' ' + r.text).toLowerCase().includes(st.q)));
      if (st.sort === 'name') list = [...list].sort((a, b) => plain(a.name).localeCompare(plain(b.name)));
      if (st.sort === 'imp') list = [...list].sort((a, b) => b.imp - a.imp);
      found.textContent = plural(list.length, 'declaration');
      const byArea = new Map(areas.map(a => [a, []]));
      list.forEach(r => byArea.get(r.area).push(r));
      groups.replaceChildren(...[...byArea].filter(([, xs]) => xs.length).map(([area, xs]) => {
        const sec = section(area, xs.length, itemList(xs, namedItem, st.area ? xs.length : 10));
        sec.querySelector('h2').append(link('#/area/' + encodeURIComponent(area), 'the area →', 'count'));
        return sec;
      }));
    }
    draw();
    setNav('named');
    show(el('h1', null, 'Named results and notable definitions'), lede, summary, filters, found, groups);
  };

  /* Every declaration someone has answered for, newest answer first, with its answers counted: the yeses of
     this version and the noes still open, people apart from AI agents, and how many no longer stand. */
  VIEWS.reviewed = async (arg, gen) => {
    const [meta, rows] = await Promise.all([TauData.meta(), TauData.reviewed()]);
    const nodes = new Map((await TauData.nodes(rows.map(r => r.id))).map(n => [n.id, n]));
    if (gen !== generation) return;
    const lib = meta.library.name, sum = pair => pair[0] + pair[1];
    const outside = meta.review ? meta.review.outside : [];
    const lede = el('p', 'lede', `The declarations of ${[lib, ...outside].join(' and of ')} that someone has answered ` +
      '"is it correctly stated?" for, the latest answer first. Open one to read it and its answers, and to answer it yourself.');
    const summary = el('p', 'summary', [plural(rows.length, 'declaration'), `${count(rows.filter(r => sum(r.yes)).length)} with a yes`,
      `${count(rows.filter(r => sum(r.no)).length)} with a no still open`].join(' · '));
    const st = {answer: 'all', who: 'anyone', q: ''};
    // Who answered: [people, AI agents] summed, or one of them.
    const of = pair => st.who === 'people' ? pair[0] : st.who === 'ai' ? pair[1] : sum(pair);
    const filters = el('div', 'filters'), seg = el('div', 'seg');
    [['all', 'All'], ['yes', 'Yes'], ['no', 'No']].forEach(([k, t]) => {
      const b = el('button', k === st.answer ? 'on' : '', t);
      b.type = 'button'; b.dataset.answer = k;
      b.addEventListener('click', () => { st.answer = k; seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); draw(); });
      seg.append(b);
    });
    const whoSelect = el('select', 'select');
    whoSelect.setAttribute('aria-label', 'Answered by');
    [['anyone', 'Answered by anyone'], ['people', 'By people'], ['ai', 'By AI agents']].forEach(([v, t]) => {
      const o = el('option', null, t); o.value = v; whoSelect.append(o);
    });
    whoSelect.addEventListener('change', () => { st.who = whoSelect.value; draw(); });
    const q = el('input', 'filter-input');
    q.type = 'search'; q.placeholder = 'Filter by name or words'; q.setAttribute('aria-label', 'Filter');
    let typing = null;
    q.addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(() => { st.q = q.value.toLowerCase(); draw(); }, 150); });
    filters.append(seg, whoSelect, q);
    // Its answers, beside it: ✓ for the yeses, ✗ for the noes, and the date of the latest.
    const tallies = r => {
      const box = el('span', 'answers');
      if (r.from) box.append(el('span', 'badge', r.from));  // outside the library: Mathlib
      const part = (answer, pair) => {
        if (!of(pair)) return;
        const s = el('span', 'answer ' + answer);
        s.append(sign(answer), [pair[0] && st.who !== 'ai' ? plural(pair[0], 'person', 'people') : '',
                                pair[1] && st.who !== 'people' ? `${pair[1]} AI` : ''].filter(Boolean).join(' · '));
        box.append(s);
      };
      part('yes', r.yes);
      part('no', r.no);
      if (of(r.earlier)) box.append(el('span', 'answer earlier', plural(of(r.earlier), 'earlier answer')));
      box.append(el('span', null, date(r.at)));
      return box;
    };
    const found = el('p', 'faint small'), listBox = el('div');
    function draw() {
      const list = rows.filter(r => nodes.has(r.id) &&
        (st.answer === 'yes' ? of(r.yes) : st.answer === 'no' ? of(r.no) : of(r.yes) + of(r.no) + of(r.earlier)) &&
        (!st.q || (r.name + ' ' + (nodes.get(r.id).title || '')).toLowerCase().includes(st.q)));
      found.textContent = plural(list.length, 'declaration');
      listBox.replaceChildren(itemList(list, r => nodeItem(nodes.get(r.id), tallies(r)), 50,
                                       rows.length ? 'None of them, with these filters.' : 'Nothing has been answered yet.'));
    }
    draw();
    setNav('reviewed');
    show(el('h1', null, 'Reviewed'), lede, summary, filters, found, listBox);
  };

  VIEWS.decl = async (name, gen) => {
    const [meta, d, named] = await Promise.all([TauData.meta(), TauData.decl(name), TauData.named()]);
    if (gen !== generation) return;
    if (!d) return VIEWS.missing(name, gen, 'No declaration of that name is in this build.');
    const n = d.node, project = !!(n.flags & FLAG.PROJECT), lib = meta.library.name;
    const up = project ? {} : ((await TauData.upstream())[name] || {});
    const e = d.entry || up;
    const row = named.find(r => r.decl === name);
    const modName = d.module ? d.module.name : ((await TauData.modules())[n.mod] || [''])[0];
    const home = modName.split('.')[0] || 'Lean';
    // Outside the library, the site asks its question of the packages the settings name (Mathlib), read in
    // Mathlib's docs.
    const answerable = project || (meta.review ? meta.review.outside : []).some(p => modName === p || modName.startsWith(p + '.'));
    if (gen !== generation) return;
    const parts = [crumbs(project ? await moduleTrail(modName) : [[`Outside ${lib}`, null], [home, null]])];
    // Head: its kind, what it is called, its Lean name, where to read it.
    const kinds = el('div', 'kind-row');
    kinds.append(kindPill(n.kind));
    if (row) kinds.append(el('span', 'badge named', `★ Named by Voyager · ${date(row.at)}`));
    if (!project) kinds.append(el('span', 'badge', home === 'Mathlib' ? 'From Mathlib' : `From ${home}`));
    kinds.append(stateBadge(stateOf(n), true));
    // The title: Voyager's name, else the docstring's first sentence, else the Lean name. A first sentence cut
    // short (for lists) gives way to the Lean name, the docstring below saying it in full.
    const cut = !row && (n.title || '').endsWith(' …');
    const h1 = el('h1');
    h1.append(row ? mdInline(row.name) : n.title && !cut ? mdInline(n.title) : el('span', 'mono', shortName(name)));
    const leanName = el('div', 'leanname'), copy = el('button', null, 'copy');
    copy.type = 'button'; copy.title = 'Copy the Lean name';
    copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(name); copy.textContent = 'copied'; } catch (x) { /* no clipboard */ } });
    leanName.append(name, copy);
    const links = el('div', 'badges links');
    if (project) {
      links.append(ext(URLS.docs(meta, name, modName), 'API docs ↗', 'badge'));
      if (e.line && d.module) links.append(ext(URLS.source(meta, d.module.path, e.line), 'Source ↗', 'badge'));
      if (row && row.post) links.append(ext(row.post, "Voyager's post ↗", 'badge'));
      if (row) row.prs.forEach(p => links.append(ext(`https://github.com/${meta.library.repo}/pull/${p}`, `PR #${p} ↗`, 'badge')));
    } else if (home === 'Mathlib') {
      links.append(ext(URLS.mathlib(name, modName), "Mathlib's docs ↗", 'badge'));
    }
    // Voyager's sentence is not repeated here: it can say more than this declaration does (another theorem of
    // the same pull request, say). Its post is a link above; the Named page lists the sentence.
    parts.push(kinds, h1, leanName, links.childNodes.length ? links : null);
    // The docstring, less what the title above already says: its first sentence when that is the title, its bold
    // opening when that only names what Voyager's title names.
    const doc = e.doc && (row ? afterLead(e.doc, row.name) : cut || !n.title ? e.doc : afterTitle(e.doc, n.title));
    if (doc && doc.trim()) parts.push(md(doc, 'prose'));
    if (e.sig || e.stmt) {
      // What the docs show: the signature Lean prints, section variables included, its names linked; a
      // definition's value folded (the docs' Equations), a structure's fields; never a proof.
      const lean = el('div', 'lean');
      if (e.sig) lean.append(signature(e.kw, e.sig, e.sigRefs || [], d.module.names || []));
      else { const pre = el('pre'); pre.textContent = e.stmt; lean.append(pre); }
      if (e.rest) {
        const what = n.kind === 'inductive' ? 'Constructors' : (n.kind === 'structure' || n.kind === 'class') ? 'Fields' : 'Definition';
        const det = el('details'), body = await valueBlock(e.rest, n);
        det.open = what !== 'Definition';
        det.append(el('summary', null, what), body);
        lean.append(det);
      }
      if (e.cut && d.module) { const c = el('div', 'cut'); c.append('The text goes on: ', ext(URLS.source(meta, d.module.path, e.line), 'read it in the source')); lean.append(c); }
      const sec = el('section', 'section');
      sec.append(el('h3', null, 'In Lean'), lean,
                 el('p', 'lean-note', 'As the docs show it, with no proof. Hover over a name to see what it is, then over the names in its card; hover over a variable to see its type. Click a name to open it.'));
      parts.push(sec);
    }
    // The review box.
    const records = project ? (e.records || []) : (up.records || []);
    const read = !answerable ? null : project ? {url: URLS.docs(meta, name, modName), label: 'Read it in the API docs ↗'}
      : {url: URLS.mathlib(name, modName), label: "Read it in Mathlib's docs ↗", from: home};
    parts.push(reviewCard(meta, name, read, records, e.tests || [], questionWord(n.kind, e.kw)));
    // The map; then, as lists, how it is proved and what rests on it beyond the map's first level.
    const mapHost = el('div');
    if (project) {
      const sec = section('What it rests on, and what rests on it', null,
        hint('Above it, what it rests on; below it, what rests on it. Click a box to open it; ↑ and ↓ unfold another level.'));
      if (row && row.cov[0] > 1) {
        const [members, people, withAi, problems] = row.cov, cov = el('div', 'coverage');
        cov.append(coverageBar(members, people, withAi, problems),
                   `Its meaning rests on ${plural(members, 'declaration')} of ${lib}: ${people} reviewed by people, ` +
                   `${withAi - people} only by AI agents, ${members - withAi - problems} by nobody` + (problems ? `, ${problems} with an open problem` : '') + '.');
        sec.append(cov);
      }
      sec.append(mapHost);
      parts.push(sec);
    }
    // What it is built from or about, and the results about it, are the map's: no lists of them (asked for on 2026-10-24).
    const lists = [];
    if (n.p.length || e.nRoutine) {
      const box = await nodeList(n.p, n.np, 'Only routine steps.');
      if (e.nRoutine) box.append(el('p', 'faint small', `and ${plural(e.nRoutine, 'routine step')} (arithmetic, logic and automation)`));
      lists.push(section(n.kind === 'theorem' ? 'How it is proved' : 'What the proofs in it use', n.np || null, box));
    }
    if (e.builtOn) lists.push(section('Built on it', e.nBuiltOn, await nodeList(e.builtOn, e.nBuiltOn)));
    if (e.examples) lists.push(section('Examples', e.nExamples, await nodeList(e.examples, e.nExamples)));
    if (e.usedIn) lists.push(section('Used to prove', e.nUsedIn, await nodeList(e.usedIn, e.nUsedIn)));
    if (gen !== generation) return;
    if (lists.length) { const two = el('div', 'two'); two.append(...lists); parts.push(two); }
    if (!project) parts.push(el('p', 'faint', `What it rests on is not followed outside ${lib}.`));
    setNav('');
    show(...parts);
    if (project) TauMap.draw(mapHost, n, d.entry, {ai: () => ai, lib});
  };

  /* The review box, as the site had it in September (scripts/build_site.py before the rebuild), asking one
     question: is it correctly stated? Yes, or no and why. Below it the answers, people counted apart from AI
     agents and each answerer a click away, each no in full; then what could be better, people's suggestions
     for it when it is correct; and what tests it, with a test to suggest. */
  function reviewCard(meta, name, read, records, tests, word) {
    const card = el('section', 'review'), open = !!read;
    card.id = 'review';
    if (open) {
      const ask = el('div', 'actions');
      ask.append(el('span', 'ask', `Is this ${word} correctly stated?`));
      const answers = ANSWERS.map(a => formFor(meta, name, a));
      answers.forEach(f => ask.append(f.button));
      ask.append(ext(read.url, read.label, 'btn docs'));
      card.append(ask, ...answers.flatMap(f => f.parts), howTo(meta), aiOffer(meta, name, read.from));
    } else {
      card.append(hint(records.length ? `Reviews of ${name} are kept in the stores that review it; they show here as they are.`
                                      : `Outside ${meta.library.name}: review it where it lives.`));
    }
    const byId = new Map(records.map(v => [v.id, v]));
    const reviews = verdict => records.filter(v => v.kind === 'review' && v.verdict === verdict);
    // Voyager's announcement heads the page; anyone else's naming is said here.
    records.filter(v => v.kind === 'named' && !(v.by.agent && v.by.agent.tool === 'Voyager')).forEach(v => {
      const line = el('p', 'namedline');
      line.append('Named ', el('strong', null, v.name), ' by ', markWho(v.by), ', ' + date(v.at));
      if (v.url) line.append(' · ', ext(v.url, issueText(v.url)));
      card.append(line);
    });
    card.append(el('p', 'sub', 'Reviews'), answers(reviews('accept'), reviews('problem'), byId));
    // A line offering a form: what it is for, and its button.
    const offer = (text, spec) => {
      const f = formFor(meta, name, spec), line = el('div', 'offer'), frag = document.createDocumentFragment();
      line.append(el('span', 'how', text), f.button);
      frag.append(line, ...f.parts);
      return frag;
    };
    // What could be better: suggestions, on the store's question form, which count as neither yes nor no.
    const suggestions = reviews('question');
    if (open || suggestions.length) {
      card.append(el('p', 'sub', 'What could be better'));
      if (open) card.append(offer('Correct, but could it be done better? More general, a better name or docstring, a cleaner statement.', SUGGEST));
      if (suggestions.length) card.append(...suggestions.map(v => report(v, byId)));
      else card.append(el('p', 'empty', 'No suggestions yet.'));
    }
    // Tests: those listed, those suggested, and a test to suggest, on the store's challenge form.
    const challenges = records.filter(v => v.kind === 'challenge' && v.state !== 'met');  // a met one is a listed test
    if (open || tests.length || challenges.length) {
      card.append(el('p', 'sub', 'Tests'));
      if (open) card.append(offer('A property it should have, such as a value, an edge case or an agreement with another notion, for someone to prove?', SUGGEST_TEST));
      card.append(testMarks(tests, challenges, byId));
    }
    return card;
  }
  /* What the answers do, under them; and, signed in with GitHub, as whom, with a way out. */
  function howTo(meta) {
    const how = el('p', 'how');
    const draw = () => {
      const s = TauSignin.configured(meta) && TauSignin.session();
      if (!TauSignin.configured(meta)) {
        how.replaceChildren('Yes and No open a short form here; a no asks you why. Send takes it to GitHub, filled in, where one click files it.');
      } else if (!s) {
        how.replaceChildren('Sign in with GitHub and Yes files your answer in one click; No asks you why. Answers are filed under your GitHub account.');
      } else {
        const out = el('button', 'btn link', 'Sign out');
        out.type = 'button';
        out.addEventListener('click', () => {
          TauSignin.signOut();
          how.closest('.review').querySelectorAll('.unfold').forEach(x => { x.hidden = true; });
          draw();
        });
        how.replaceChildren('Yes files your answer at once; No asks you why. Answering as ', ext(URLS.github(s.login), '@' + s.login), ' · ', out);
      }
    };
    draw();
    return how;
  }
  /* A short form that unfolds in the review box, by its template: what it asks for, and Send. Signed in with GitHub
     (web/signin.js), Send files it from here, under the reader's account, and Yes needs no form at all: one click
     files it, with Undo, and Add why for a reason. Signed out, Send signs in first, then files it. And it can always
     open on GitHub instead, filled in with the declaration, the commit and what was written, for one click there to
     file it: the only way where the site has no sign-in. */
  const FIELDS = {
    'evidence-review.yml': [{id: 'rationale', label: 'Why? (optional)', hint: 'What you compared it with, what you checked.'}],
    'evidence-problem.yml': [{id: 'rationale', label: 'Why is it not correctly stated?', hint: 'A case it gets wrong, a counterexample, or what it should say.', required: true}],
    'evidence-question.yml': [{id: 'question', label: 'What could be better?', hint: 'More general, a better name or docstring, a cleaner statement.', required: true}],
    'evidence-challenge.yml': [{id: 'property', label: 'What it should satisfy', hint: 'A value, an edge case, an agreement with another notion.', required: true},
                               {id: 'statement', label: 'As a Lean statement (optional)', mono: true},
                               {id: 'catches', label: 'What it would catch (optional)'}],
  };
  const WHAT = {'evidence-review.yml': 'yes', 'evidence-problem.yml': 'no', 'evidence-question.yml': 'suggestion',
                'evidence-challenge.yml': 'test'};
  const OPENED = 'Opened on GitHub, filled in: submit it there, and it shows here within minutes.';
  const live = [];  // the forms of the page shown, for what was to be done on return from signing in (start)
  let formSeq = 0;
  function formFor(meta, name, [label, template, cls]) {
    const signin = TauSignin.configured(meta), oneClick = signin && template === 'evidence-review.yml';
    const id = 'form-' + (++formSeq), button = el('button', 'btn ' + cls, label), form = el('form', 'unfold');
    const prompt = el('div', 'unfold prompt'), note = el('div', 'sent-note');
    const btn = (text, klass, type = 'button') => { const b = el('button', 'btn' + (klass ? ' ' + klass : ''), text); b.type = type; return b; };
    button.type = 'button';
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-controls', id);
    form.id = id;
    form.hidden = prompt.hidden = note.hidden = true;
    note.setAttribute('role', 'status');
    const fields = FIELDS[template].map(f => {
      const t = el('textarea', f.mono ? 'mono' : null), l = el('label', null, f.label);
      t.id = `${id}-${f.id}`;
      t.rows = f.mono ? 2 : 3;
      if (f.hint) t.placeholder = f.hint;
      l.htmlFor = t.id;
      form.append(l, t);
      return [f, t, l];
    });
    // After a yes, Add why: the same form, the reason now the point of it.
    let whyWanted = false, busy = false, filed = null;
    const again = el('p', 'again', 'This files your yes again, with why: it takes the place of the first.');
    again.hidden = true;
    const send = btn('', 'send', 'submit'), cancel = btn('Cancel'), row = el('div', 'form-actions');
    row.append(cancel, send);
    form.append(again, row);
    const values = () => Object.fromEntries(fields.filter(([, t]) => t.value.trim()).map(([f, t]) => [f.id, t.value.trim()]));
    const sync = () => {
      send.textContent = !signin ? 'Send on GitHub ↗' : TauSignin.session() ? 'Send' : 'Sign in with GitHub and send';
      send.disabled = busy || fields.some(([f, t]) => (f.required || whyWanted) && !t.value.trim());
      fields.forEach(([f, , l]) => { l.textContent = whyWanted ? 'Why is it correctly stated?' : f.label; });
      again.hidden = !whyWanted;
    };
    // One form open at a time in a review box.
    function closeAll() {
      const box = button.closest('.review');
      box.querySelectorAll('.unfold').forEach(x => { x.hidden = true; });
      box.querySelectorAll('[aria-controls^="form-"]').forEach(b => b.setAttribute('aria-expanded', 'false'));
      box.querySelectorAll('.sent-note').forEach(x => { x.hidden = true; });
    }
    function unfold(what) {
      closeAll();
      what.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      if (what === form) { sync(); fields[0][1].focus(); }
    }
    const shut = () => { form.hidden = prompt.hidden = true; whyWanted = false; button.setAttribute('aria-expanded', 'false'); };
    const say = (...content) => { note.replaceChildren(...content); note.hidden = false; };
    const onGitHub = v => {
      window.open(URLS.form(meta, template, name, v), '_blank', 'noopener');
      form.reset();
      shut();
      say(OPENED);
      // What was written, on the clipboard as well, to paste should GitHub lose it.
      if (!Object.keys(v).length || !navigator.clipboard) return;
      navigator.clipboard.writeText(issueBody(template, {...v, decl: name, commit: meta.library.commit}))
        .then(() => say(OPENED + ' What you wrote is on your clipboard too, should it not be there.'), () => {});
    };
    const toGitHub = (text, v) => { const b = btn(text, 'link gh'); b.addEventListener('click', () => onGitHub(v())); return b; };
    // Signed out: off to GitHub to sign in, and back here to file it.
    const begin = v => {
      say('Off to GitHub to sign in…');
      TauSignin.signIn(meta, {decl: name, template, values: v})
        .catch(e => say(`Not signed in: ${e.message}. `, toGitHub('Send it on GitHub instead ↗', () => v)));
    };
    async function deliver(v) {
      if (busy) return;
      busy = true;
      sync();
      say('Sending…');
      try {
        filed = await TauSignin.file(meta, {title: FORMS[template].title + name, labels: [FORMS[template].label],
                                            body: issueBody(template, {...v, decl: name, commit: meta.library.commit})});
        form.reset();
        shut();
        sent(filed);
      } catch (e) {
        if (e.status === 401) {  // the sign-in ended meanwhile
          const back = btn('Sign in with GitHub and send', 'send');
          back.addEventListener('click', () => begin(v));
          say('Your GitHub sign-in has ended. ', back, ' ', toGitHub('or send it on GitHub ↗', () => v));
        } else say(`Not sent: ${e.message}. `, toGitHub('Send it on GitHub instead ↗', () => v));
      } finally {
        busy = false;
        sync();
      }
    }
    function sent(f) {
      const s = TauSignin.session(), undo = btn('Undo', 'link');
      undo.addEventListener('click', () => withdraw(f));
      const line = ['✓ Filed: your ' + WHAT[template] + ', ', ext(f.url, `issue #${f.number}`), s ? ` by @${s.login}` : '',
                    '. It shows here within minutes. '];
      if (template !== 'evidence-review.yml') return say(...line, undo);
      const why = btn('Add why', 'link');
      why.addEventListener('click', () => { whyWanted = true; unfold(form); });
      say(...line, why, ' · ', undo);
    }
    // Undo: the record's own command, on its issue.
    async function withdraw(f) {
      if (busy) return;
      busy = true;
      say('Taking it back…');
      try {
        await TauSignin.comment(meta, f.number, '/withdraw');
        filed = null;
        say('Taken back: ', ext(f.url, `issue #${f.number}`), ' says /withdraw, and the page shows it within minutes.');
      } catch (e) {
        say(`Not taken back: ${e.message}. Comment /withdraw on `, ext(f.url, `issue #${f.number}`), '.');
      } finally {
        busy = false;
      }
    }
    button.addEventListener('click', () => {
      if (busy) return;
      if (!(form.hidden && prompt.hidden)) return closeAll();
      if (oneClick && filed) { closeAll(); note.hidden = false; return; }  // filed already: say so again, not twice
      if (oneClick && TauSignin.session()) { closeAll(); return deliver({}); }
      unfold(oneClick ? prompt : form);
    });
    if (oneClick) {
      const go = btn('Sign in with GitHub', 'send'), no = btn('Cancel'), actions = el('div', 'form-actions');
      go.addEventListener('click', () => begin({}));
      no.addEventListener('click', shut);
      actions.append(toGitHub('or answer on GitHub ↗', () => ({})), no, go);
      prompt.append(el('p', null, 'Sign in with GitHub once, and Yes files your answer from here in one click, under your GitHub account.'), actions);
    }
    if (signin) row.prepend(toGitHub('or send it on GitHub ↗', values));
    form.addEventListener('input', sync);
    cancel.addEventListener('click', () => { form.reset(); shut(); });
    form.addEventListener('submit', ev => {
      ev.preventDefault();
      sync();
      if (send.disabled) return;
      const v = values();
      if (!signin) onGitHub(v);
      else if (TauSignin.session()) deliver(v);
      else begin(v);
    });
    // Back from signing in: file what was written, or say why not and give it back to send another way.
    live.push({name, template, resume(v, error) {
      v = v || {};
      fields.forEach(([f, t]) => { t.value = v[f.id] || ''; });
      if (error) {
        unfold(oneClick && !Object.keys(v).length ? prompt : form);
        say(error + ' ', toGitHub('Send it on GitHub instead ↗', () => v));
      } else deliver(v);
      note.scrollIntoView({block: 'center'});
    }});
    return {button, parts: oneClick ? [prompt, form, note] : [form, note]};
  }
  /* Instructions for an AI agent to review it as AI-REVIEWS.md says, for this declaration at this commit: copied
     with one click, and shown, to copy by hand where the browser will not. */
  function aiOffer(meta, name, from) {
    const at = from ? `, from the ${from} that ${meta.library.name} commit ${meta.library.commit} builds on`
                    : ` at ${meta.library.name} commit ${meta.library.commit}`;
    const text = `Review ${name} for the ${meta.store.name} review site, following\n` +
      `https://github.com/${meta.store.repo}/blob/main/AI-REVIEWS.md\n` +
      `Give your exact model, as AI-REVIEWS.md says: GPT-6 Astra, not GPT-6.\n` +
      `The site shows it${at}: ${meta.site.url}#/d/${encodeURIComponent(name)}`;
    const box = el('div', 'ai-offer'), line = el('div', 'offer'), btn = el('button', 'btn offer', 'Copy instructions for your AI');
    const prompt = el('pre', 'ai-prompt');
    btn.type = 'button';
    prompt.textContent = text;
    prompt.hidden = true;
    btn.addEventListener('click', async () => {
      prompt.hidden = false;
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = 'Copied: paste them to your AI';
      } catch (e) {  // no clipboard here: select them, to copy by hand
        getSelection().selectAllChildren(prompt);
        btn.textContent = 'Selected: copy them for your AI';
      }
    });
    line.append(el('span', 'how', 'Or have an AI agent review it, under your GitHub account and marked AI:'), btn);
    box.append(line, prompt);
    return box;
  }
  /* Whether a record speaks for the declaration as it is now; and an answer, whether it still stands: a yes
     of this version, a no still open. */
  const applies = v => v.inForce && v.applies !== false;
  const stands = v => v.verdict === 'problem' ? v.state === 'open' : applies(v);
  const sign = answer => { const t = el('span', 'tick', answer === 'no' ? '✗' : '✓'); t.setAttribute('aria-hidden', 'true'); return t; };
  const issueText = url => { const m = /\/issues\/(\d+)$/.exec(url || ''); return m ? 'Issue #' + m[1] : 'issue'; };
  /* Who made a record, as a mark says it: @login, or the agent, AI, and the account it acted through. */
  function markWho(by) {
    const span = el('span', 'who');
    if (by.kind === 'agent') {
      const a = by.agent || {};
      span.append([a.tool || 'An AI agent', a.model].filter(Boolean).join(', ') + ' ', el('span', 'ai', 'AI'));
      if (by.login) span.append(' via @' + by.login);
    } else span.append(by.login ? '@' + by.login : by.label || 'someone');
    return span;
  }
  const MARK_NOTE = {stale: () => 'earlier version', 'stale-underneath': () => 'what it rests on has changed',
                     renamed: v => 'as ' + v.renamedFrom, unavailable: () => 'did not build', orphaned: () => 'gone',
                     incomparable: () => 'cannot be compared'};
  /* One answer, as its answerer's mark: a tick for a yes, a cross for a no, a link to its issue (unless it
     heads a twisty, which holds the link), greyed when it no longer stands (a yes of an earlier version, a no
     resolved). */
  function mark(v, heading) {
    const answer = v.verdict === 'problem' ? 'no' : 'yes';
    const cls = `mark ${answer} ` + (v.by.kind === 'agent' ? 'agent' : 'person') + (stands(v) ? '' : ' stale');
    const m = v.url && !heading ? ext(v.url, null, cls) : el('span', cls);
    m.append(sign(answer), markWho(v.by));
    const note = !v.inForce && v.state === 'withdrawn' ? 'withdrawn'
      : answer === 'no' && v.state !== 'open' ? (STATE_WORDS[v.state] || v.state).toLowerCase()
      : !v.inForce ? 'superseded' : MARK_NOTE[v.status] && MARK_NOTE[v.status](v);
    if (note) m.append(el('span', 'note', note));
    if (v.source) m.append(el('span', 'note', `from the ${v.source.name} store`));
    if ((v.replies || []).length) m.append(el('span', 'note', plural(v.replies.length, 'reply', 'replies')));
    m.title = [answer === 'no' ? 'No: it is not correctly stated.' : 'Yes: it is correctly stated.',
               (v.hash ? `Version ${v.hash}, ` : '') + date(v.at) + '.', statusNote(v)].filter(Boolean).join(' ');
    return m;
  }
  /* A twisty: a line that opens to show more. */
  function twisty(cls, head, ...body) {
    const d = el('details', 'twisty ' + cls), s = el('summary'), b = el('div', 'twisty-body');
    s.append(...head);
    b.append(...body.filter(Boolean));
    d.append(s, b);
    return d;
  }
  /* One yes in the list of answers: its mark, which opens, when it gives reasons (an agent gives them only when
     they add to the answers already there), to
     show why: what it was compared with, what was checked, the Checks run; then its issue. A bare yes is just
     its mark, and a no is shown in full below. */
  function answerRow(v) {
    const ref = v.reference && (v.reference.text || v.reference.url);
    const checked = Object.entries(v.checked || {}).filter(([, s]) => s === 'checked').map(([axis]) => axis);
    const caveats = (v.caveats || []).map(c => typeof c === 'string' ? c : [c.category, c.note || c.text].filter(Boolean).join(': '));
    if (v.verdict === 'problem' || !(v.text || ref || checked.length || caveats.length)) return mark(v);
    const line = el('p', 'line');
    if (v.url) line.append(ext(v.url, issueText(v.url)), ' · ');
    line.append(date(v.at) + (v.hash ? ' · version ' + v.hash.slice(0, 8) : ''));
    return twisty('why', [mark(v, true), el('span', 'gist', 'why')],
                  ref ? el('p', 'line', `Compared with ${ref}.`) : null, checked.length ? el('p', 'line', `Checked: ${checked.join(', ')}.`) : null,
                  v.text ? md(v.text) : null, caveats.length ? el('p', 'line', 'What could be better: ' + caveats.join('; ')) : null, line);
  }
  /* A mark that counts the answers that stand, people apart from AI agents, and says how many no longer do. */
  function tally(answer, words, vs, gone) {
    const now = vs.filter(stands), people = now.filter(v => v.by.kind !== 'agent').length, agents = now.length - people;
    const counts = [people ? plural(people, 'person', 'people') : '', agents ? `${agents} AI` : ''].filter(Boolean).join(' · ');
    const t = el('span', `mark tally ${answer} ` + (people ? 'person' : agents ? 'agent' : 'stale'));
    t.title = answer === 'no' ? 'Answered no: it is not correctly stated' : 'Answered yes: it is correctly stated';
    t.append(sign(answer), el('span', 'trailer', words));
    if (counts) t.append(' ', el('span', 'who', counts));
    const k = vs.length - now.length;
    if (k) t.append(counts ? ' · ' : ' ', el('span', 'note', gone(k)));
    return t;
  }
  /* The answers: a mark for the yeses of this version and one for the noes still open, then each answer's own
     mark, a twisty when it gives reasons, then each no in full, with why. */
  function answers(yes, no, byId) {
    const box = el('div');
    if (!yes.length && !no.length) { box.append(el('p', 'empty', 'No answers yet.')); return box; }
    const row = el('div', 'marks');
    if (yes.length) row.append(tally('yes', 'Correctly stated', yes, k => k === 1 ? '1 on an earlier version' : `${k} on earlier versions`));
    if (no.length) row.append(tally('no', 'Not correctly stated', no, k => `${k} resolved`));
    const list = el('div', 'answers-list');
    [...yes, ...no].sort((a, b) => stands(b) - stands(a) || (b.at || '').localeCompare(a.at || '')).forEach(v => list.append(answerRow(v)));
    box.append(row, list, ...no.map(v => report(v, byId)));
    return box;
  }
  const TEST_RESULT = {passes: 'passes', sorry: 'has sorry', missing: 'missing at this commit'};
  /* Tested by: a mark that counts the tests that pass; then each listed test, a twisty that opens to what it
     checks and its statement as the docs show it, and each suggested one, a twisty that opens to where it
     stands. */
  function testMarks(tests, challenges, byId) {
    const box = el('div'), total = tests.length + challenges.length;
    if (!total) { box.append(el('p', 'empty', 'No tests yet.')); return box; }
    const passes = tests.filter(x => x.result === 'passes').length, failing = tests.length - passes;
    const open = challenges.filter(v => v.state === 'open').length;
    const parts = [passes ? (passes === 1 ? '1 test that passes' : `${passes} tests that pass`) : 'nothing that passes yet'];
    if (failing) parts.push(`${failing} that ${failing === 1 ? 'does' : 'do'} not`);
    if (open) parts.push(`${open} suggested`);
    const t = el('span', 'mark tally ' + (passes ? 'tested' : 'stale')), row = el('div', 'marks');
    t.title = 'Tested by: tests of it that pass, listed or suggested';
    t.append(sign('yes'), el('span', 'trailer', 'Tested by'), ' ', el('span', 'who', parts.join(' · ')));
    row.append(t);
    const list = el('div', 'tests-list');
    // What it checks, in a line: its first line, cut at 90 characters. The twisty holds the rest, if there is more.
    const gist = text => { const first = plain(String(text || '').split('\n')[0]); return first ? ' — ' + (first.length > 90 ? first.slice(0, 89) + '…' : first) : ''; };
    const more = text => { const t = String(text || '').trim(); return t.includes('\n') || plain(t).length > 90; };
    tests.forEach(x => {
      const stmt = el('div', 'lean'), line = el('p', 'line');
      line.append(link(URLS.decl(x.test), x.test, 'mono'), x.challenge ? ' · suggested and met; listed by ' : ' · listed by ',
                  markWho(x.by), ', ' + date(x.at));
      if (x.url) line.append(' · ', ext(x.url, issueText(x.url)));
      const d = twisty('test', [el('span', x.result === 'passes' ? 'pass' : 'fail', TEST_RESULT[x.result] || x.result), ' · ',
                                el('span', 'mono', shortName(x.test)), el('span', 'gist', gist(x.text))],
                       more(x.text) ? md(x.text) : null, stmt, line);
      // Its statement, as the docs show it, fetched the first time it is opened.
      let asked = false;
      d.addEventListener('toggle', async () => {
        if (!d.open || asked) return;
        asked = true;
        const found = await TauData.decl(x.test), e = found && found.entry;
        if (e && e.sig) stmt.append(signature(e.kw, e.sig, e.sigRefs || [], found.module.names || []));
        else if (e && e.stmt) { const pre = el('pre'); pre.textContent = e.stmt; stmt.append(pre); }
        else if (found) { const pre = el('pre'); pre.textContent = `${found.node.name} : ${found.node.brief}`; stmt.append(pre); }
      });
      list.append(d);
    });
    challenges.forEach(v => {
      const line = el('p', 'line');
      line.append(v.state === 'open' ? 'Suggested by ' : `${STATE_WORDS[v.state] || v.state} · suggested by `, markWho(v.by), ', ' + date(v.at));
      if (v.url) line.append(' · ', ext(v.url, issueText(v.url)));
      const pre = v.statement ? el('pre', 'small-code') : null;
      if (pre) pre.textContent = v.statement;
      const d = twisty('test suggested' + (v.state === 'open' ? '' : ' closed'),
                       [el('span', 'suggested', v.state === 'open' ? 'suggested' : (STATE_WORDS[v.state] || v.state).toLowerCase()),
                        el('span', 'gist', gist(v.text))],
                       v.text ? md(v.text) : null, pre, v.catches ? el('p', 'note', 'Would catch: ' + v.catches) : null, line);
      replies(d.lastChild, v, byId);
      list.append(d);
    });
    box.append(row, list);
    return box;
  }
  /* A no or a suggestion (a question record): where it stands, who said it and when, what they said, the
     replies, and its issue with what was decided on it. */
  function report(v, byId) {
    const open = v.state === 'open', question = v.verdict === 'question';
    const box = el('div', 'report' + (question ? ' question' : '') + (open ? '' : ' closed')), head = el('p', 'head');
    head.append(el('span', 'state', open ? 'Open' : question && v.state === 'answered' ? 'Closed' : STATE_WORDS[v.state] || 'Closed'), ' · ',
                question ? 'suggested by ' : (v.category && v.category !== 'other' ? v.category + ' · ' : '') + 'answered no by ',
                markWho(v.by), ', ' + date(v.at));
    const note = v.status !== 'current' && statusNote(v);
    if (note) head.append(' · ', el('span', 'note', note));
    if (v.source) head.append(` · from the ${v.source.name} store`);
    box.append(head);
    if (v.text) box.append(md(v.text));
    if (v.fix) box.append(el('p', 'fix', 'Suggested fix'), md(v.fix));
    replies(box, v, byId);
    resolutions(box, v, markWho);
    if (v.url) { const foot = el('p', 'line'); foot.append(ext(v.url, issueText(v.url))); box.append(foot); }
    return box;
  }
  /* What was decided on a no or a suggestion, each decision in full: how it stands (fixed, at which commit; behaves
     as intended; not a problem; answered), who decided and when, and why, as written: so anyone can see why a no
     was closed. */
  function resolutions(box, v, whoOf) {
    for (const s of v.statuses || []) {
      const block = el('div', 'resolution'), head = el('p', 'line');
      head.append(el('b', null, STATE_WORDS[s.state] || s.state), s.commit ? ` at ${s.commit.slice(0, 7)}` : '', ' · ', whoOf(s.by),
                  ', ' + date(s.at));
      if (s.url) head.append(' · ', ext(s.url, issueText(s.url)));
      block.append(head);
      if (s.text) block.append(md(s.text));
      box.append(block);
    }
  }
  function replies(box, v, byId) {
    for (const id of v.replies || []) {
      const r = byId.get(id);
      if (!r) continue;
      const reply = el('div', 'reply'), head = el('p', 'line');
      head.append(markWho(r.by), ', ' + date(r.at));
      reply.append(head, md(r.text));
      box.append(reply);
    }
  }

  VIEWS.module = async (name, gen) => {
    const [meta, found] = await Promise.all([TauData.meta(), TauData.moduleByName(name)]);
    if (gen !== generation) return;
    if (!found || !found.file) return VIEWS.missing(name, gen, 'No module of that name is in this build.');
    const f = found.file, items = (await TauData.nodes(f.decls.map(x => x.id))).filter(x => !(x.flags & FLAG.AUX));
    if (gen !== generation) return;
    const first = x => (x.flags & FLAG.NAMED ? 0 : 1);
    const of = test => items.filter(test).sort((a, b) => first(a) - first(b));
    const notions = of(x => kindClass(x.kind) === 'concept'), results = of(x => kindClass(x.kind) === 'result');
    const instances = of(x => x.kind === 'instance');
    const leanName = el('div', 'leanname');
    leanName.append(name + ' · ', ext(URLS.source(meta, f.path, null), 'source on GitHub'));
    const two = el('div', 'two');
    two.append(section('Notions', notions.length, itemList(notions, x => nodeItem(x), 200, 'None.')),
               section('Results', results.length, itemList(results, x => nodeItem(x), 200, 'None.')));
    let more = null;
    if (instances.length) {
      more = el('details', 'more section');
      more.append(el('summary', null, plural(instances.length, 'instance')), itemList(instances, x => nodeItem(x), instances.length));
    }
    const area = areaOf(name);
    setNav('browse');
    show(crumbs([[meta.library.name, '#/browse'], [area, '#/area/' + encodeURIComponent(area)]]), el('span', 'kind file', 'File'),
         el('h1', null, f.title || name), leanName, f.doc ? md(f.doc.replace(/^\s*#\s.*$/m, ''), 'prose section') : null, two, more);
  };

  VIEWS.area = async (area, gen) => {
    const [meta, modules, named] = await Promise.all([TauData.meta(), TauData.modules(), TauData.named()]);
    if (gen !== generation) return;
    const mine = modules.slice(0, meta.counts.modules).filter(m => areaOf(m[0]) === area);
    if (!mine.length) return VIEWS.missing(area, gen, 'No area of that name is in this build.');
    const info = meta.areas.find(a => a[0] === area), ns = named.filter(r => r.area === area);
    const fileItem = m => {
      const li = el('li'), a = link('#/m/' + encodeURIComponent(m[0]), null, 'k-file'), body = el('span', 'item-body');
      body.append(el('span', 'item-title', m[2] || m[0].split('.').slice(2).join('.') || m[0]), el('span', 'item-sub', m[0]));
      a.append(body);
      li.append(a);
      return li;
    };
    setNav('browse');
    show(crumbs([[meta.library.name, '#/browse']]), el('span', 'kind area', 'Area'), el('h1', null, area),
         el('p', 'muted', `${plural(info ? info[1] : 0, 'declaration')} · ${ns.length} named · ${plural(mine.length, 'file')}`),
         ns.length ? section('Named here', ns.length, itemList(ns, namedItem, 24)) : null,
         section('Files', mine.length, itemList(mine, fileItem, 400)));
  };

  VIEWS.browse = async (arg, gen) => {
    const meta = await TauData.meta();
    if (gen !== generation) return;
    const lib = meta.library.name, cards = el('div', 'cards');
    meta.areas.forEach(([a, n, k]) => {
      const c = link('#/area/' + encodeURIComponent(a), null, 'card');
      c.append(el('h3', null, a), el('p', 'num', `${plural(n, 'declaration')}${k ? ` · ${k} named` : ''}`));
      cards.append(c);
    });
    setNav('browse');
    show(el('h1', null, `${lib}, area by area`),
         el('p', 'lede', `${plural(meta.counts.declarations, 'declaration')} in ${plural(meta.counts.modules, 'file')}, at commit ` +
           `${meta.library.commit.slice(0, 7)}. Each area is a folder of ${lib}: open one for its named results and its files.`), cards);
  };

  let searchGen = 0;
  VIEWS.search = async (q, gen) => {
    $('q').value = q;
    setNav('');
    const status = el('p', 'muted', 'Searching…'), notions = el('ul', 'list'), results = el('ul', 'list');
    const two = el('div', 'two'), g1 = el('div', 'results-group'), g2 = el('div', 'results-group');
    g1.append(el('h3', null, 'Notions'), notions);
    g2.append(el('h3', null, 'Results'), results);
    two.append(g1, g2);
    const direct = /[._]|^[A-Z]/.test(q.trim()) ? el('p', 'faint') : null;
    if (direct) direct.append('Looking for a Lean name, the library\'s or Mathlib\'s? ', link(URLS.decl(q.trim()), `Open ${q.trim()}`), ' directly.');
    show(el('h1', null, q ? `Search: ${q}` : 'Search'), status, two, direct);
    if (!q.trim()) { status.textContent = 'Type a name, part of one, or words from a docstring.'; two.remove(); return; }
    const mine = ++searchGen;
    const rows = await TauData.search();
    if (gen !== generation || mine !== searchGen) return;
    const ql = q.trim().toLowerCase(), words = ql.split(/\s+/);
    const scoreName = name => {
      const n = name.toLowerCase(), last = n.slice(n.lastIndexOf('.') + 1);
      if (n === ql) return 0;
      if (last === ql) return 1;
      if (last.startsWith(ql)) return 2;
      if (n.includes(ql)) return 3;
      return words.length > 1 && words.every(w => n.includes(w)) ? 4 : 9;
    };
    const hits = [];
    rows.forEach((r, i) => { const s = scoreName(r[0]); if (s < 9) hits.push([s, r[0].length, i]); });
    const none = () => { const li = el('li', 'faint', 'None'); return li; };
    const render = async extra => {
      const all = hits.concat(extra).sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 200), total = hits.length + extra.length;
      status.textContent = all.length ? `${plural(total, 'match', 'matches')}${total > 200 ? ', the first 200' : ''}` : 'Nothing found yet…';
      const ids = await Promise.all(all.map(h => TauData.idOf(rows[h[2]][0])));
      const ns = (await TauData.nodes(ids.filter(x => x != null))).sort((a, b) => (b.flags & FLAG.NAMED) - (a.flags & FLAG.NAMED));
      if (mine !== searchGen) return;
      const a = ns.filter(x => kindClass(x.kind) === 'concept'), b = ns.filter(x => kindClass(x.kind) !== 'concept');
      notions.replaceChildren(...(a.length ? a.map(x => nodeItem(x)) : [none()]));
      results.replaceChildren(...(b.length ? b.map(x => nodeItem(x)) : [none()]));
    };
    await render([]);
    const titles = await TauData.titles();
    if (gen !== generation || mine !== searchGen) return;
    const extra = [], seen = new Set(hits.map(h => h[2]));
    titles.forEach((t, i) => { if (!seen.has(i) && t && words.every(w => t.toLowerCase().includes(w))) extra.push([5, t.length, i]); });
    await render(extra);
    if (!hits.length && !extra.length) status.textContent = 'Nothing matches.';
  };

  VIEWS.activity = async (arg, gen) => {
    const [meta, act] = await Promise.all([TauData.meta(), TauData.activity()]);
    if (gen !== generation) return;
    const recordList = (vs, empty) => {
      if (!vs.length) return el('p', 'faint', empty);
      const box = el('div', 'records'), byId = new Map(vs.map(v => [v.id, v]));
      vs.forEach(v => { const t = thread(v, byId); t.prepend(link(URLS.decl(v.decl), v.decl, 'decl-link')); box.append(t); });
      return box;
    };
    const weights = new Map(act.queue);
    const queue = (await TauData.nodes(act.queue.map(x => x[0]))).map(x =>
      nodeItem(x, el('span', null, `${plural(weights.get(x.id), 'named result')} ${weights.get(x.id) === 1 ? 'rests' : 'rest'} on it`)));
    const queueList = el('ul', 'list');
    queueList.append(...queue);
    const reviewers = el('div', 'chips');
    act.reviewers.forEach(r => reviewers.append(el('span', 'chip' + (r.kind === 'agent' ? ' agent' : ''), `${r.label} · ${r.n}`)));
    const stats = el('div', 'stats');
    [[act.problems.length, 'no, still open'], [act.questions.length, 'suggestions open'], [act.challenges.length, 'suggested tests open'],
     [act.reviewers.length, 'reviewers']].forEach(([n, t]) => { const s = el('div', 'stat'); s.append(el('b', null, count(n)), el('span', null, t)); stats.append(s); });
    if (gen !== generation) return;
    setNav('activity');
    show(el('h1', null, 'Activity'),
      el('p', 'lede', `Everything recorded about ${meta.library.name}, newest first, and what is still open.`), stats,
      section('Answered no, still open', act.problems.length, recordList(act.problems, 'None.')),
      section('Answered no, resolved', (act.answered || []).length,
              hint('Each no closed: fixed, behaving as intended, or not a problem, and why, the latest first.'),
              recordList(act.answered || [], 'None yet.')),
      section('What could be better, still open', act.questions.length, recordList(act.questions, 'No suggestions open.')),
      act.challenges.length ? section('Suggested tests, still open', act.challenges.length, recordList(act.challenges, '')) : null,
      section('What to review next', null, hint(`Unreviewed declarations of ${meta.library.name} that named results rest on, those most of them share first.`),
              queue.length ? queueList : el('p', 'faint', 'Nothing yet.')),
      section('Latest', null, recordList(act.recent, 'Nothing yet.')),
      section('Reviewers', act.reviewers.length, act.reviewers.length ? reviewers : el('p', 'faint', 'Nobody yet.')));
  };

  VIEWS.help = async (arg, gen) => {
    const meta = await TauData.meta();
    if (gen !== generation) return;
    const lib = meta.library.name;
    const p = (...parts) => { const x = el('p'); x.append(...parts); return x; };
    const prose = (...ps) => { const box = el('div', 'prose'); box.append(...ps); return box; };
    const code = t => { const c = el('pre', 'small-code'); c.textContent = t; return c; };
    const outside = meta.review ? meta.review.outside : [];
    const signin = TauSignin.configured(meta);
    const sends = signin ? 'Send files it from the page, or opens it on GitHub, filled in' : 'Send takes it to GitHub, filled in';
    setNav('help');
    show(el('h1', null, 'How to review'),
      el('p', 'lede', 'A review answers one question: is this declaration correctly stated? Yes, or no and why.'),
      prose(signin
              ? p('Open a declaration: its review box asks the question. Sign in with GitHub once, and ', el('b', null, 'Yes'),
                  ' files your answer from the page in one click, with Undo, and Add why to give a reason; ', el('b', null, 'No'),
                  ' opens a short form that asks why, and will not send without it. Signing in lets the page file issues on ',
                  ext(URLS.issues(meta), meta.store.repo), ' under your account, and nothing else, for eight hours; it is kept in your ',
                  'browser alone. Rather not sign in? Each form opens on GitHub instead, filled in with the declaration, the commit this ',
                  `page shows and what you wrote: submit it there. Your answer is kept in this site's evidence store under your GitHub `,
                  'account, and shows on the page within minutes. No pull request.')
              : p('Open a declaration: its review box asks the question. ', el('b', null, 'Yes'), ' opens a short form in the box, a reason ',
                  'optional; ', el('b', null, 'No'), ' opens one that asks why, and will not send without it. ', el('b', null, 'Send'),
                  ' opens it on GitHub, filled in with the declaration, the commit this page shows and what you wrote: submit it there. ',
                  `Your answer is kept in this site's evidence store under your GitHub account, and shows on the page within minutes. `,
                  'No pull request.'),
            p('Correctly stated means that it says what it should: it is the intended notion, or states the intended result, as its ',
              'name, its docstring and the literature say. Not that its proof is right: Lean checks that.'),
            p('The ', link('#/reviewed', 'Reviewed'), ' page lists every declaration answered so far, the latest first.'),
            ...(outside.length ? [p(`${outside.join(' and ')}'s declarations are answered for here too: open one from a declaration of ${lib} `,
              `that uses it, or by its Lean name in Search. Its page links to Mathlib's docs, and its review box asks the same `,
              `question, of the version ${lib} builds on.`)] : [])),
      section('What could be better', null, prose(
        p('Something can be correctly stated and still be done better: stated more generally, with a better name or docstring, more ',
          'cleanly, or with a lemma it should come with. Say so under ', el('b', null, 'What could be better'), ' in the review box: ',
          el('b', null, 'Suggest an improvement'), ` opens a short form in the box, and ${sends}. A suggestion is neither a yes nor a no. `,
          'Replies are comments on its issue, and you or a maintainer close it when it is dealt with.'))),
      section('Tests', null, prose(
        p('Under ', el('b', null, 'Tests'), ' in the review box, ', el('b', null, 'Suggest a test'), ` opens a short form in the box (${sends}): `,
          'a property the declaration should have, such as a value, an edge case or an agreement with another notion, in words and ',
          `if you can in Lean. It stays open until a declaration of ${lib} proves it; the page then lists that declaration as a test, `,
          'and checks at every commit that it still passes.'))),
      section('Versions', null, prose(
        p("An answer is pinned to the declaration as it was: to its meaning hash, which changes when the declaration changes or anything it rests on does. ",
          `A yes about an earlier version stays, greyed: "the declaration has changed since", or "something it rests on has changed since". Nothing is written into ${lib}.`))),
      section('AI agents', null, prose(
        p('The forms are for people. An AI agent answers from the command line, following ',
          ext(`https://github.com/${meta.store.repo}/blob/main/AI-REVIEWS.md`, 'AI-REVIEWS.md'),
          `: it reads the declaration against its source, runs the Checks its roadmap gives it (the examples in ${lib} that carry their tags), `,
          "and files its answer with its reasons, which list each Check. Its answers are marked AI and counted apart from people's. ",
          'An agent always answers, but its reasons give only what the answers already there do not, such as a second source that ',
          'states it as Lean does; with nothing to add, its yes has no reasons. To ask an agent for one, give it this:'),
        code(`Review TauCeti.Foo.bar for the Tau Ceti review site, following\nhttps://github.com/${meta.store.repo}/blob/main/AI-REVIEWS.md\n` +
             'Give your exact model, as AI-REVIEWS.md says: GPT-6 Astra, not GPT-6.'),
        p('Each declaration\'s review box has a button, ', el('b', null, 'Copy instructions for your AI'), ', that copies these, filled in ',
          'with the declaration and the commit the site shows.'),
        p('Many yeses at once: comment lines like these on ', ext(URLS.bulk(meta), `issue #${meta.store.bulk}`), ', one each, after a line naming the agent:'),
        code('<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->\nReviewed-by: TauCeti.Foo.bar — why it is correctly stated'))),
      section("On an answer's issue", null, prose(
        p('A comment whose first line is a command changes where the answer stands: ', el('code', null, '/withdraw'),
          ' takes it back; on a no, ', el('code', null, '/fixed <commit>'), ', ', el('code', null, '/intended'), ' or ',
          el('code', null, '/invalid'), ' resolves it, and ', el('code', null, '/reopen'), ' opens it again. Other comments are kept as replies.'))),
      section('Where this comes from', null, prose(
        p('Built with the ', ext('https://github.com/LeanTrustBuilders', 'LeanTrustBuilders'), ` tools: the dataset of ${lib} at `,
          ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, meta.library.commit.slice(0, 7)),
          ` (${meta.dataset.producer}), the evidence store `, ext(`https://github.com/${meta.store.repo}`, meta.store.repo),
          meta.imports.length ? ', and the stores it imports: ' : '.', ...meta.imports.flatMap((s, i) => [i ? ', ' : '', ext(`https://github.com/${s.repo}`, s.name)]),
          meta.imports.length ? '.' : ''))));
  };

  VIEWS.missing = async (what, gen, why) => {
    setNav('');
    const parts = [el('h1', null, 'Not here'), el('p', 'lede', why || 'There is no page at this address.')];
    if (what) parts.push(link('#/search/' + encodeURIComponent(String(what).split('.').pop()), 'Search for it'));
    show(...parts);
  };

  /* --- the footer, and a name's card on hover -------------------------------------------------------- */
  async function footer() {
    const meta = await TauData.meta(), lib = meta.library;
    $('foot').replaceChildren(`${lib.name} at `, ext(`https://github.com/${lib.repo}/commit/${lib.commit}`, lib.commit.slice(0, 7), 'mono'),
      lib.date ? ` (${date(lib.date)})` : '', ` · built ${date(meta.built)} by the `, ext('https://github.com/LeanTrustBuilders', 'LeanTrustBuilders'),
      ' tools · reviews kept in ', ext(`https://github.com/${meta.store.repo}`, meta.store.repo), ' · ', link('#/help', 'How to review'));
  }
  /* A name's card on hover: what it is, its signature with its names linked, a definition's value. A name in
     a card opens its own card on top, and so on; a variable's card is its type. Without Lean: the cards show
     what the docs and the source say, not what Lean elaborates. */
  const cards = [];   // the open cards, outermost first
  let closer = null, opening = 0;
  function closeCards(depth) {
    while (cards.length > depth) cards.pop().remove();
    if (!depth) document.querySelectorAll('.var.hit').forEach(x => x.classList.remove('hit'));
  }
  const scheduleClose = () => { clearTimeout(closer); closer = setTimeout(() => closeCards(0), 350); };
  async function nameCard(name) {
    const [meta, d] = await Promise.all([TauData.meta(), TauData.decl(name)]);
    if (!d) return null;
    const n = d.node, e = d.entry || {}, project = !!(n.flags & FLAG.PROJECT);
    const card = el('div', 'tip');
    card.append(el('div', 't-name', `${n.name} · ${KIND_WORD[n.kind] || 'Declaration'}${project ? '' : ' · outside ' + meta.library.name}`));
    if (n.title) { const t = el('div', 't-title'); t.append(mdInline(n.title)); card.append(t); }
    if (project && e.sig) {
      const lean = el('div', 'lean');
      lean.append(signature(e.kw, e.sig, e.sigRefs || [], d.module.names || []));
      if (e.rest) lean.append(await valueBlock(e.rest, n));
      card.append(lean);
      const s = el('div'); s.append(stateBadge(stateOf(n), true)); card.append(s);
    } else {
      if (n.brief) card.append(el('div', 't-stmt', n.brief));
      const mod = ((await TauData.modules())[n.mod] || [''])[0];
      if (mod.split('.')[0] === 'Mathlib') card.append(ext(URLS.mathlib(name, mod), "Mathlib's docs ↗", 't-link'));
    }
    return card;
  }
  function varCard(span) {
    const pre = span.closest('pre');
    if (!pre || !pre.sig) return null;
    const card = el('div', 'tip'), lean = el('div', 'lean'), type = sigSlice(pre.sig, +span.dataset.a, +span.dataset.b);
    type.prepend(span.dataset.var + ' : ');
    lean.append(type);
    card.append(el('div', 't-name', `${span.dataset.var} · variable`), lean);
    return card;
  }
  async function openCard(anchor) {
    clearTimeout(closer);
    const mine = ++opening, inCard = anchor.closest('.tip'), depth = inCard ? cards.indexOf(inCard) + 1 : 0;
    const card = anchor.matches('.var') ? varCard(anchor) : await nameCard(anchor.dataset.name);
    if (mine !== opening || !card || !anchor.isConnected) return;
    closeCards(depth);
    document.querySelectorAll('.var.hit').forEach(x => x.classList.remove('hit'));
    if (anchor.matches('.var')) anchor.closest('pre').querySelectorAll(`.var[data-var="${CSS.escape(anchor.dataset.var)}"]`).forEach(x => x.classList.add('hit'));
    card.addEventListener('mouseenter', () => clearTimeout(closer));
    card.addEventListener('mouseleave', scheduleClose);
    card.style.zIndex = 50 + depth;
    document.body.append(card);
    const r = anchor.getBoundingClientRect();
    card.style.left = Math.max(8, Math.min(r.left, innerWidth - card.offsetWidth - 8)) + 'px';
    card.style.top = (r.bottom + 8 + card.offsetHeight > innerHeight ? Math.max(8, r.top - card.offsetHeight - 8) : r.bottom + 8) + 'px';
    cards.push(card);
  }
  const HOVER = 'a.ref[data-name], .var';
  document.addEventListener('mouseover', ev => {
    const a = ev.target.closest ? ev.target.closest(HOVER) : null;
    if (a && !(ev.relatedTarget && a.contains(ev.relatedTarget))) openCard(a);
  });
  document.addEventListener('mouseout', ev => {
    const a = ev.target.closest ? ev.target.closest(HOVER + ', .tip') : null;
    if (a && !(ev.relatedTarget && a.contains(ev.relatedTarget))) scheduleClose();
  });
  document.addEventListener('focusin', ev => { if (ev.target.matches && ev.target.matches('a.ref[data-name]')) openCard(ev.target); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeCards(0); });
  addEventListener('scroll', () => closeCards(0), {passive: true});

  /* --- wiring --------------------------------------------------------------------------------------- */
  async function route() {
    const r = parse(location.hash);
    if (location.hash && !location.hash.startsWith('#/') && r[0] !== 'missing') history.replaceState(null, '', address(r));
    current = r.join(':');
    closeCards(0);
    live.length = 0;
    const gen = ++generation;
    ready = false;
    try {
      await VIEWS[r[0]](r[1], gen);
    } catch (e) {
      if (gen === generation) {
        const box = el('pre', 'small-code');
        box.textContent = String(e && e.stack || e);
        show(el('h1', null, 'This page could not be shown'), box);
      }
      console.error(e);
    }
    if (gen === generation) ready = true;
  }
  let typing = null;
  const search = value => {
    const target = '#/search/' + encodeURIComponent(value);
    if (location.hash.startsWith('#/search/')) { history.replaceState(null, '', target); route(); } else location.hash = target;
  };
  $('q').addEventListener('input', e => { clearTimeout(typing); typing = setTimeout(() => search(e.target.value), 250); });
  $('search-form').addEventListener('submit', e => { e.preventDefault(); clearTimeout(typing); search($('q').value); });
  document.addEventListener('keydown', e => {
    if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))) {
      e.preventDefault(); $('q').focus(); $('q').select();
    }
  });
  $('theme').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('tauceti-review:theme', next); } catch (e) { /* not kept */ }
  });
  /* The first page; back from signing in with GitHub, the page as it was, then what was to be done there. */
  async function start() {
    let back = null;
    try {
      const meta = await TauData.meta();
      if (TauSignin.configured(meta)) back = await TauSignin.finish(meta);
    } catch (e) {
      console.error(e);
    }
    await route();
    const then = back && back.then, form = then && live.find(f => f.name === then.decl && f.template === then.template);
    if (form) form.resume(then.values, back.error);
  }
  window.addEventListener('hashchange', route);
  footer().catch(e => console.error(e));
  start();

  /* For the browser check (tests/validate_site.py). */
  window.TauReview = Object.freeze({
    get ready() { return ready; },
    route: () => current,
    mapNodes: () => [...document.querySelectorAll('.map .node[data-name]')].map(g => g.dataset.name),
    afterTitle, afterLead,
    fnv: TauData.fnv,
  });
})();
