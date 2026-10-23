/* Tau Ceti Review: the pages, laid out as Mathlib Explorer lays out its own (LeanTrustBuilders/
   mathlib-explorer, static/app.js): a hash router (#/…) and one function per page. Everything shown
   comes from TauData (what the build wrote), laid out with TauRender and TauMap. */
(function () {
  'use strict';
  const {el, link, ext, md, mdInline, kindClass, kindPill, KIND_WORD, stateBadge, STATE_TEXT, URLS, FORMS, date, plural, who,
         shortName, plain} = TauRender;
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
    return ({'': ['home'], named: ['named'], d: ['decl', arg], m: ['module', arg], area: ['area', arg], search: ['search', arg],
             browse: ['browse'], activity: ['activity'], help: ['help']})[head] || ['missing', h];
  }
  const address = r => ({home: '#/', named: '#/named', decl: '#/d/', module: '#/m/', area: '#/area/', search: '#/search/',
                         browse: '#/browse', activity: '#/activity', help: '#/help'})[r[0]] + (r[1] != null ? encodeURIComponent(r[1]) : '');

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
  /* A ranked list of declarations: the first dozen, all the data keeps on a click, and a count of the rest.
     With `outside`, what is from Mathlib and Lean is a line of chips below it instead, Lean's notions named
     as a mathematician would and its plumbing left out, as Mathlib Explorer shows its basic notions. */
  async function nodeList(ids, total, empty, outside) {
    const all = ids && ids.length ? await TauData.nodes(ids) : [];
    const chips = outside ? all.filter(n => !(n.flags & FLAG.PROJECT)) : [];
    const box = itemList(all.filter(n => !chips.includes(n)), n => nodeItem(n), 12, chips.length ? '' : empty);
    if (chips.length) {
      const line = el('p', 'hint basics'), seen = new Set();
      line.append('From Mathlib and Lean: ');
      chips.forEach(n => {
        const word = n.name in BASIC_WORDS ? BASIC_WORDS[n.name] : shortName(n.name);
        if (!word || seen.has(word)) return;
        seen.add(word);
        const chip = link(URLS.decl(n.name), word, 'chip basic');
        chip.title = n.name + (n.brief ? ' : ' + n.brief : '');
        line.append(chip, ' ');
      });
      if (seen.size) box.append(line);
    }
    if (ids && total > ids.length) box.append(el('p', 'faint small', `and ${plural(total - ids.length, 'more')} not listed`));
    return box;
  }
  /* Mathlib Explorer's words for Lean's basic notions (static/app.js, BASIC_WORDS); '' is plumbing. */
  const BASIC_WORDS = {Eq: 'equality', Ne: '≠', Nat: 'natural numbers ℕ', Int: 'integers ℤ', Real: 'real numbers ℝ',
    Complex: 'complex numbers ℂ', Rat: 'rationals ℚ', HMul: 'multiplication', Mul: 'multiplication', HAdd: 'addition',
    Add: 'addition', HSub: 'subtraction', Sub: 'subtraction', HDiv: 'division', Div: 'division', HPow: 'powers', Pow: 'powers',
    Neg: 'negation', Inv: 'inverse', Zero: 'zero', One: 'one', OfNat: 'numerals', LE: '≤', LT: '<', Exists: 'there exists',
    And: 'and', Or: 'or', Not: 'not', Iff: 'if and only if', Membership: '∈', HSMul: 'scalar multiplication',
    SMul: 'scalar multiplication', Prod: 'pairs', Subtype: 'subsets as types', List: 'lists', Array: 'arrays', Bool: 'booleans',
    String: 'strings', Fin: 'Fin n', Option: 'optional values', True: 'true', False: 'false', Function: 'functions',
    Unit: 'unit', Sum: 'disjoint union', Sigma: 'dependent pairs', Quotient: 'quotients', Setoid: 'equivalence relations',
    NatCast: 'ℕ → R', IntCast: 'ℤ → R', HEq: 'equality', Set: 'sets', Decidable: '', DecidableEq: '', DecidablePred: '',
    DecidableRel: '', outParam: '', semiOutParam: '', Inhabited: '', Nonempty: 'nonempty', 'Classical.propDecidable': '',
    'Classical.decEq': '', 'Classical.decPred': '', instDecidableEqNat: '', id: 'identity', ite: 'if … then … else',
    dite: 'if … then … else', optParam: '', autoParam: '', CoeFun: '', CoeSort: '', FunLike: '', DFunLike: '', HFunLike: ''};

  /* --- records -------------------------------------------------------------------------------------- */
  function verdictBadge(v) {
    const words = {review: {accept: 'Reviewed', problem: 'Problem', question: 'Question'}[v.verdict] || 'Review',
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
    if (v.category) box.append(el('div', 'faint small', 'What is wrong: ' + v.category));
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
    for (const s of v.statuses || []) {
      const line = el('div', 'faint small');
      line.append(`${STATE_WORDS[s.state] || s.state} by `, who(s.by), ` on ${date(s.at)}`);
      if (s.text) line.append(': ', mdInline(s.text));
      box.append(line);
    }
    if (v.actions && v.actions.length && v.url) {
      const acts = el('div', 'record-actions');
      acts.append('On its issue: ');
      v.actions.forEach((a, i) => { if (i) acts.append(' · '); acts.append(ext(v.url, '/' + a)); });
      box.append(acts);
    }
    return box;
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
    return pre;
  }

  /* --- pages ---------------------------------------------------------------------------------------- */
  const VIEWS = {};

  VIEWS.home = async (arg, gen) => {
    const [meta, rows] = await Promise.all([TauData.meta(), TauData.named()]);
    if (gen !== generation) return;
    const c = meta.counts, lib = meta.library.name;
    const lede = el('p', 'lede', `${lib} is a library of formalized mathematics, in Lean. Here people and AI agents review it: ` +
      'read each declaration as its documentation shows it, see what it rests on, and leave a review, a problem, a test or a question. ' +
      `Nothing is written into ${lib}: a review is kept against the declaration's hash, and says so when the declaration changes.`);
    const stats = el('div', 'stats');
    [[c.declarations, 'declarations'], [c.named, 'named by Voyager'], [c.accepts.people, 'reviews by people'],
     [c.accepts.ai, 'reviews by AI agents'], [c.problems, 'open problems']]
      .forEach(([n, t]) => { const s = el('div', 'stat'); s.append(el('b', null, count(n)), el('span', null, t)); stats.append(s); });
    const card = (href, title, text) => { const a = link(href, null, 'card'); a.append(el('h3', null, title), el('p', null, text)); return a; };
    const cards = el('div', 'cards');
    cards.append(
      card('#/named', 'Named results', `The ${count(c.named)} theorems and definitions Voyager announced on the Lean Zulip: the ones to read first.`),
      card('#/browse', 'Browse', `${lib} area by area: ${plural(meta.areas.length, 'area')}, ${plural(c.modules, 'file')}.`),
      card('#/activity', 'Activity', `The latest reviews, ${plural(c.problems, 'open problem')}, ${plural(c.challenges, 'suggested test')} still open, and what to review next.`),
      card('#/help', 'How to review', 'A review, a problem, a test or a question: a form on GitHub, filled in. No pull request.'));
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
                           ['uncounted', 'Reviewed by AI only'], ['stale', 'Reviewed on an earlier version'], ['problem', 'With an open problem']], 'state', 'Review state'),
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
    if (gen !== generation) return;
    const parts = [crumbs(project ? await moduleTrail(modName) : [[`Outside ${lib}`, null], [home, null]])];
    // Head: its kind, what it is called, its Lean name, where to read it.
    const kinds = el('div', 'kind-row');
    kinds.append(kindPill(n.kind));
    if (row) kinds.append(el('span', 'badge named', `★ Named by Voyager · ${date(row.at)}`));
    if (!project) kinds.append(el('span', 'badge', home === 'Mathlib' ? 'From Mathlib' : `From ${home}`));
    kinds.append(stateBadge(stateOf(n), true));
    const h1 = el('h1');
    h1.append(row ? mdInline(row.name) : n.title ? mdInline(n.title) : el('span', 'mono', shortName(name)));
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
      links.append(ext(URLS.mathlib(name, modName), "Mathlib's docs ↗", 'badge'), ext(URLS.explorer(name), 'Mathlib Explorer ↗', 'badge'));
    }
    parts.push(kinds, h1, leanName, links.childNodes.length ? links : null);
    if (row && row.text) {
      const box = el('div', 'announce');
      box.append(el('div', 'announce-label', 'Voyager announced it'), md(row.text, 'prose'));
      parts.push(box);
    }
    // The docstring, unless all it says is the title above.
    if (e.doc && (row || e.doc.trim() !== (n.title || '').trim())) parts.push(md(e.doc, 'prose'));
    if (e.sig || e.stmt) {
      // What the docs show: the signature Lean prints, section variables included, its names linked; a
      // definition's value folded (the docs' Equations), a structure's fields; never a proof.
      const lean = el('div', 'lean');
      if (e.sig) lean.append(signature(e.kw, e.sig, e.sigRefs || [], d.module.names || []));
      else { const pre = el('pre'); pre.textContent = e.stmt; lean.append(pre); }
      if (e.rest) {
        const what = n.kind === 'inductive' ? 'Constructors' : (n.kind === 'structure' || n.kind === 'class') ? 'Fields' : 'Definition';
        const det = el('details'), body = el('pre');
        det.open = what !== 'Definition';
        body.textContent = e.rest;
        det.append(el('summary', null, what), body);
        lean.append(det);
      }
      if (e.cut && d.module) { const c = el('div', 'cut'); c.append('The text goes on: ', ext(URLS.source(meta, d.module.path, e.line), 'read it in the source')); lean.append(c); }
      const sec = el('section', 'section');
      sec.append(el('h3', null, 'In Lean'), lean,
                 el('p', 'lean-note', 'As the docs show it, with no proof. Hover over a name to see what it is; click it to open it.'));
      parts.push(sec);
    }
    // The review card.
    const records = project ? (e.records || []) : (up.records || []);
    parts.push(reviewCard(meta, n, name, modName, project, records, e.tests || []));
    // The map, and the same as lists.
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
    const lists = [], about = n.kind === 'theorem' || n.kind === 'axiom' || n.kind === 'instance';
    if (project) lists.push(section(about ? 'What it is about' : 'What it is built from', n.nm || null, await nodeList(n.m, n.nm, 'Only Lean itself.', true)));
    if (n.p.length || e.nRoutine) {
      const box = await nodeList(n.p, n.np, 'Only routine steps.');
      if (e.nRoutine) box.append(el('p', 'faint small', `and ${plural(e.nRoutine, 'routine step')} (arithmetic, logic and automation)`));
      lists.push(section(n.kind === 'theorem' ? 'How it is proved' : 'What the proofs in it use', n.np || null, box));
    }
    if (e.facts) lists.push(section('Results about it', e.nFacts, await nodeList(e.facts, e.nFacts)));
    if (e.builtOn) lists.push(section('Built on it', e.nBuiltOn, await nodeList(e.builtOn, e.nBuiltOn)));
    if (e.examples) lists.push(section('Examples', e.nExamples, await nodeList(e.examples, e.nExamples)));
    if (e.usedIn) lists.push(section('Used to prove', e.nUsedIn, await nodeList(e.usedIn, e.nUsedIn)));
    if (gen !== generation) return;
    if (lists.length) { const two = el('div', 'two'); two.append(...lists); parts.push(two); }
    if (!project) parts.push(el('p', 'faint', `What it rests on is not followed outside ${lib}: Mathlib Explorer shows it.`));
    setNav('');
    show(...parts);
    if (project) TauMap.draw(mapHost, n, d.entry, {ai: () => ai});
  };

  /* Where a declaration stands, the forms to review it, and every record about it. */
  function reviewCard(meta, n, name, modName, project, records, tests) {
    const card = el('section', 'review'), head = el('div', 'review-head');
    card.id = 'review';
    head.append(el('h2', null, 'Review'), aiSwitch());
    const counted = (agent) => records.filter(v => v.kind === 'review' && v.verdict === 'accept' && v.inForce && v.applies &&
                                                 (v.by.kind === 'agent') === agent).length;
    const people = counted(false), agents = counted(true), line = el('div', 'state-line');
    line.append(stateBadge(stateOf(n), true),
                el('span', null, people || agents ? `Reviewed-by · ${plural(people, 'person', 'people')} · ${agents} AI`
                  : records.some(v => v.kind === 'review' && v.verdict === 'accept') ? 'No review of this version yet.' : 'Nobody has reviewed it yet.'));
    card.append(head, line);
    if (project) {
      const acts = el('div', 'review-actions'), forms = el('div', 'actions');
      FORMS.forEach(([text, template, prefix, cls]) => forms.append(ext(URLS.form(meta, template, prefix, name), text, 'btn ' + cls)));
      acts.append(ext(URLS.docs(meta, name, modName), 'Read it in the API docs ↗', 'btn docs-btn'), forms);
      card.append(acts, hint('Each button opens a form on GitHub, filled in with this declaration and the commit shown here. ' +
        `It is recorded under your account within minutes; nothing is written into ${meta.library.name}.`));
    } else if (records.length) {
      card.append(hint(`Reviews of ${name} are kept in the stores that review it; they show here as they are.`));
    } else {
      card.append(hint(`Outside ${meta.library.name}: review it where it lives, such as the Mathlib probability store.`));
    }
    const byId = new Map(records.map(v => [v.id, v]));
    // Tests are listed below with whether they pass; Voyager's announcement heads the page.
    const top = records.filter(v => v.kind !== 'comment' && v.kind !== 'test' && !(v.kind === 'named' && v.by.agent && v.by.agent.tool === 'Voyager'));
    const order = v => (v.inForce && v.applies !== false ? 0 : 1);
    top.sort((a, b) => order(a) - order(b) || (b.at || '').localeCompare(a.at || ''));
    top.forEach(v => card.append(thread(v, byId)));
    if (tests.length) {
      const t = el('div', 'tests');
      t.append(el('h3', null, 'Tests'));
      tests.forEach(x => {
        const row = el('div', 'test-line');
        row.append(el('span', 'result ' + x.result, {passes: 'passes', sorry: 'with sorry', missing: 'missing'}[x.result]),
                   link(URLS.decl(x.test), shortName(x.test), 'mono'));
        if (x.text) row.append(' — ', mdInline(x.text));
        const by = el('div', 'faint small');
        by.append(x.challenge ? 'Suggested, and met; listed by ' : 'Listed by ', who(x.by), ' · ' + date(x.at));
        if (x.url) by.append(' · ', ext(x.url, 'issue'));
        row.append(by);
        t.append(row);
      });
      card.append(t);
    }
    return card;
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
    if (direct) direct.append('Looking for a Lean name? ', link(URLS.decl(q.trim()), `Open ${q.trim()}`), ' directly.');
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
    [[act.problems.length, 'open problems'], [act.questions.length, 'open questions'], [act.challenges.length, 'suggested tests open'],
     [act.reviewers.length, 'reviewers']].forEach(([n, t]) => { const s = el('div', 'stat'); s.append(el('b', null, count(n)), el('span', null, t)); stats.append(s); });
    if (gen !== generation) return;
    setNav('activity');
    show(el('h1', null, 'Reviews, problems and suggested tests'),
      el('p', 'lede', `Everything recorded about ${meta.library.name}, newest first, and what is still open.`), stats,
      section('Open problems', act.problems.length, recordList(act.problems, 'No open problems.')),
      section('Open questions', act.questions.length, recordList(act.questions, 'No open questions.')),
      section('Suggested tests, still open', act.challenges.length, recordList(act.challenges, 'No open suggestions.')),
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
    setNav('help');
    show(el('h1', null, 'How to review'),
      el('p', 'lede', 'Leave a review, a problem, a test or a question. Each is a form on GitHub, filled in, and no pull request.'),
      prose(p('Open a declaration and use the buttons in its Review card: each opens a form on GitHub, filled in with the declaration and the commit this page shows. ',
              `Submit it, and the record is kept in this site's evidence store under your GitHub account, and shown here within minutes.`)),
      section('What each form records', null, prose(
        p(el('b', null, 'Review this'), ': it is the intended mathematical notion, or states the intended result. Say what you compared it with and which ways it could go wrong you checked. A person need not say why; an AI agent must.'),
        p(el('b', null, 'Report a problem'), ': it is wrong, and why. The problem stays open, and the declaration is flagged, until someone marks it fixed, intended, or not a problem.'),
        p(el('b', null, 'Suggest a test'), `: a property it should have, in words and if you can in Lean. It stays open until a declaration of ${lib} proves it.`),
        p(el('b', null, 'List a test'), `: a declaration of ${lib} that already pins it down, and what it checks.`),
        p(el('b', null, 'Ask a question'), ': anything you want its authors or reviewers to answer.'))),
      section('Versions', null, prose(
        p("A review is pinned to the declaration as it was: to its meaning hash, which changes when the declaration changes or anything it rests on does. ",
          `A review of an earlier version stays, greyed: "the declaration has changed since", or "something it rests on has changed since". Nothing is written into ${lib}.`))),
      section('Many at once, and AI agents', null, prose(
        p('Comment lines like these on ', ext(URLS.bulk(meta), `issue #${meta.store.bulk}`), ', one record each:'),
        code('Reviewed-by: TauCeti.Foo.bar — what you checked\nTest: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — its value at 0\nChallenge: TauCeti.Foo.bar — it is additive\nNamed: TauCeti.Foo.bar — The bar theorem — a sentence'),
        p("An AI agent names itself in its comment, and its records are shown apart from people's:"),
        code('<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->'))),
      section("On a record's issue", null, prose(
        p('A comment whose first line is a command changes its state: ', el('code', null, '/withdraw'), ', ', el('code', null, '/fixed'), ', ',
          el('code', null, '/intended'), ', ', el('code', null, '/invalid'), ', ', el('code', null, '/met <declaration>'), ', ',
          el('code', null, '/declined'), ', ', el('code', null, '/answered'), ', ', el('code', null, '/reopen'), '.'))),
      section('Where this comes from', null, prose(
        p('Built with the ', ext('https://github.com/LeanTrustBuilders', 'LeanTrustBuilders'), ` tools: the dataset of ${lib} at `,
          ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, meta.library.commit.slice(0, 7)),
          ` (${meta.dataset.producer}), the evidence store `, ext(`https://github.com/${meta.store.repo}`, meta.store.repo),
          meta.imports.length ? ', and the stores it imports: ' : '.', ...meta.imports.flatMap((s, i) => [i ? ', ' : '', ext(`https://github.com/${s.repo}`, s.name)]),
          meta.imports.length ? '.' : ''),
        p('The look is Mathlib Explorer\'s, in the colours of the Tau Ceti Atlas.'))));
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
  const tip = $('tip');
  let tipFor = null;
  document.addEventListener('mouseover', async ev => {
    const a = ev.target.closest ? ev.target.closest('a.ref[data-name]') : null;
    if (!a || a === tipFor) return;
    tipFor = a;
    const id = await TauData.idOf(a.dataset.name), n = id == null ? null : await TauData.node(id);
    if (tipFor !== a || !n) return;
    const lib = (await TauData.meta()).library.name, project = !!(n.flags & FLAG.PROJECT);
    tip.replaceChildren(el('div', 't-name', `${n.name} · ${KIND_WORD[n.kind] || 'Declaration'}${project ? '' : ' · outside ' + lib}`));
    if (n.title) { const t = el('div', 't-title'); t.append(mdInline(n.title)); tip.append(t); }
    if (n.brief) tip.append(el('div', 't-stmt', n.brief));
    if (project) { const s = el('div'); s.append(stateBadge(stateOf(n), true)); tip.append(s); }
    const r = a.getBoundingClientRect();
    tip.hidden = false;
    tip.style.left = Math.max(8, Math.min(r.left, innerWidth - tip.offsetWidth - 8)) + 'px';
    tip.style.top = (r.bottom + 8 + tip.offsetHeight > innerHeight ? r.top - tip.offsetHeight - 8 : r.bottom + 8) + 'px';
  });
  document.addEventListener('mouseout', ev => { if (tipFor && !tipFor.contains(ev.relatedTarget)) { tip.hidden = true; tipFor = null; } });

  /* --- wiring --------------------------------------------------------------------------------------- */
  async function route() {
    const r = parse(location.hash);
    if (location.hash && !location.hash.startsWith('#/') && r[0] !== 'missing') history.replaceState(null, '', address(r));
    current = r.join(':');
    tip.hidden = true; tipFor = null;
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
  window.addEventListener('hashchange', route);
  footer().catch(e => console.error(e));
  route();

  /* For the browser check (tests/validate_site.py). */
  window.TauReview = Object.freeze({
    get ready() { return ready; },
    route: () => current,
    mapNodes: () => [...document.querySelectorAll('.map .node[data-name]')].map(g => g.dataset.name),
    fnv: TauData.fnv,
  });
})();
