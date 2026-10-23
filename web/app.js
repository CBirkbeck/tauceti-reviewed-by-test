/* Tau Ceti Review: the pages. A hash router (#/…), the rail, and one function per page. Everything
   shown comes from TauData (what the build wrote), laid out with TauRender and TauMap. */
(function () {
  'use strict';
  const {el, link, ext, md, mdInline, glyph, URLS, FORMS, date, plural, who, shortName, STATE_TEXT, modulePath, plain} = TauRender;
  const {FLAG, STATES} = TauData;
  const $ = id => document.getElementById(id);
  const page = $('page'), context = $('context');
  let generation = 0, ready = false, current = '';
  let ai = false;
  try { ai = localStorage.getItem('tauceti-review:ai') === '1'; } catch (e) { /* no storage: the default */ }
  const pick = pair => pair[ai ? 1 : 0];
  const stateOf = n => pick(n.state);
  const rowState = r => STATES[pick(r.s)] || 'unreviewed';
  const kindWord = {theorem: 'Theorem', definition: 'Definition', structure: 'Structure', class: 'Class',
                    inductive: 'Inductive type', instance: 'Instance', axiom: 'Axiom', opaque: 'Definition'};

  /* --- addresses ---------------------------------------------------------------------------------- */
  function parse(hash) {
    const h = (hash || '').replace(/^#/, '');
    if (h && !h.startsWith('/') && h.includes('=')) {          // the old site's addresses: #d=…&m=…&q=…
      const p = new URLSearchParams(h);
      if (p.get('d')) return ['decl', p.get('d')];
      if (p.get('m')) return ['module', p.get('m')];
      if (p.get('q')) return ['search', p.get('q')];
      if (p.get('area')) return ['area', p.get('area')];
      return ['named'];
    }
    const [head, ...rest] = h.replace(/^\//, '').split('/');
    const arg = decodeURIComponent(rest.join('/'));
    return ({'': ['named'], d: ['decl', arg], m: ['module', arg], area: ['area', arg], search: ['search', arg],
             browse: ['browse'], activity: ['activity'], help: ['help']})[head] || ['missing', h];
  }
  const address = r => ({named: '#/', decl: '#/d/', module: '#/m/', area: '#/area/', search: '#/search/',
                         browse: '#/browse', activity: '#/activity', help: '#/help'})[r[0]] + (r[1] != null ? encodeURIComponent(r[1]) : '');

  /* --- frame ---------------------------------------------------------------------------------------- */
  function setContext(trail) {
    context.replaceChildren();
    trail.forEach(([text, href], i) => {
      if (i) context.append(el('span', 'sep', '›'));
      context.append(href ? link(href, text) : el('span', 'here', text));
    });
    const copy = el('button', 'quiet copy', 'Copy link');
    copy.type = 'button';
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(location.href); copy.textContent = 'Copied'; } catch (e) { copy.textContent = 'Copy the address bar'; }
      setTimeout(() => { copy.textContent = 'Copy link'; }, 1500);
    });
    context.append(copy);
  }
  function setNav(which) {
    document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === which));
  }
  function show(...nodes) { page.replaceChildren(...nodes); page.scrollTop = 0; window.scrollTo(0, 0); }
  function section(title, ...body) { const s = el('section', 'block'); s.append(el('h2', null, title), ...body); return s; }
  const areaOf = module => { const p = module.split('.'); return p.length > 1 ? p[1] : p[0]; };
  async function moduleTrail(module) {
    const meta = await TauData.meta();
    const tail = module.split('.').slice(1).join('.') || module, area = areaOf(module);
    return [[meta.library.name, '#/browse'], [area, '#/area/' + encodeURIComponent(area)],
            ...(tail !== area ? [[tail, '#/m/' + encodeURIComponent(module)]] : [])];
  }

  /* --- small parts ---------------------------------------------------------------------------------- */
  function nodeItem(n) {
    const a = link(URLS.decl(n.name), null, 'nitem');
    a.append(glyph(n.kind, stateOf(n), {size: 20, named: !!(n.flags & FLAG.NAMED), upstream: !(n.flags & FLAG.PROJECT)}));
    const text = el('span', 'nitem-text');
    text.append(el('span', 't', plain(n.title) || shortName(n.name)), el('span', 'n', n.name));
    a.append(text);
    a.title = `${kindWord[n.kind] || 'Declaration'} · ${STATE_TEXT[stateOf(n)]}`;
    return a;
  }
  /* A ranked list of declarations: the first dozen, then all that the data keeps, then a count. */
  async function nodeList(ids, total, empty) {
    const box = el('div', 'nbox');
    if (!ids || !ids.length) { box.append(el('p', 'faint', empty)); return box; }
    const items = await TauData.nodes(ids), list = el('div', 'nlist');
    const fill = k => list.replaceChildren(...items.slice(0, k).map(nodeItem));
    fill(12);
    box.append(list);
    if (items.length > 12) {
      const b = el('button', 'btn small more', `Show all ${items.length}`);
      b.type = 'button';
      b.addEventListener('click', () => { fill(items.length); b.remove(); });
      box.append(b);
    }
    if (total > ids.length) box.append(el('p', 'faint small', `and ${plural(total - ids.length, 'more')} not listed`));
    return box;
  }
  function verdictBadge(v) {
    const words = {review: {accept: 'Reviewed', problem: 'Problem', question: 'Question'}[v.verdict] || 'Review',
                   test: 'Test', challenge: 'Suggested test', named: 'Named', comment: 'Reply'};
    const kind = v.kind === 'review' ? v.verdict : v.kind;
    return el('span', 'verdict ' + kind, words[v.kind] || v.kind);
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
    if (v.fix) { box.append(el('div', 'faint small', 'Suggested fix:'), md(v.fix)); }
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

  /* A signature as the docs show it: the keyword, then each name a link to its declaration. Positions
     are code points (S2), hence Array.from. */
  function signature(kw, text, refs, names) {
    const pre = el('pre'), cps = Array.from(text);
    if (kw) pre.append(el('span', 'kw', kw + ' '));
    let at = 0;
    [...refs].sort((a, b) => a[0] - b[0]).forEach(([a, b, k]) => {
      if (a < at || !names[k]) return;
      if (a > at) pre.append(cps.slice(at, a).join(''));
      const l = link(URLS.decl(names[k]), cps.slice(a, b).join(''), 'ref');
      l.title = names[k];
      pre.append(l);
      at = b;
    });
    if (at < cps.length) pre.append(cps.slice(at).join(''));
    return pre;
  }

  /* --- pages ---------------------------------------------------------------------------------------- */
  const VIEWS = {};

  VIEWS.named = async (arg, gen) => {
    const [meta, rows] = await Promise.all([TauData.meta(), TauData.named()]);
    if (gen !== generation) return;
    setContext([['Named', null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Announced by Voyager on the Lean Zulip'), el('h1', null, 'Named results and notable definitions'));
    const lede = el('p', 'lede');
    lede.append(`The mathematics Voyager has announced as new in ${meta.library.name}: named theorems and notable definitions, `,
                'the declarations to read first. Open one to read it, see what it rests on, and review it.');
    head.append(lede);
    const results = rows.filter(r => r.what === 'result').length;
    const by = st => rows.filter(r => rowState(r) === st).length;
    const stats = el('div', 'stats');
    [[rows.length, 'named'], [results, 'results'], [rows.length - results, 'definitions'],
     [by('covered') + by('disputed'), ai ? 'reviewed, counting AI' : 'reviewed by people'], [by('unreviewed'), 'not reviewed yet']]
      .forEach(([n, t]) => { const s = el('div', 'stat'); s.append(el('b', null, n.toLocaleString('en')), el('span', null, t)); stats.append(s); });
    head.append(stats);
    // Filters: kind, area, state, order, words.
    const st = {what: 'all', area: '', state: '', sort: 'new', q: '', shown: 60};
    const filters = el('div', 'filters');
    const seg = el('div', 'seg');
    [['all', 'All'], ['result', 'Results'], ['definition', 'Definitions']].forEach(([k, t]) => {
      const b = el('button', k === st.what ? 'on' : '', t);
      b.type = 'button'; b.dataset.what = k;
      b.addEventListener('click', () => { st.what = k; seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); st.shown = 60; draw(); });
      seg.append(b);
    });
    const select = (options, key, label) => {
      const s = el('select', 'select'); s.setAttribute('aria-label', label);
      options.forEach(([v, t]) => { const o = el('option', null, t); o.value = v; s.append(o); });
      s.addEventListener('change', () => { st[key] = s.value; st.shown = 60; draw(); });
      return s;
    };
    const areas = [...new Set(rows.map(r => r.area))].sort();
    const q = el('input', 'filter-input');
    q.type = 'search'; q.placeholder = 'Filter by name or words'; q.setAttribute('aria-label', 'Filter');
    q.addEventListener('input', () => { st.q = q.value.toLowerCase(); st.shown = 60; draw(); });
    filters.append(seg, select([['', 'Every area'], ...areas.map(a => [a, a])], 'area', 'Area'),
                   select([['', 'Any review state'], ['covered', 'Reviewed'], ['unreviewed', 'Not reviewed yet'],
                           ['uncounted', 'Reviewed by AI only'], ['stale', 'Reviewed on an earlier version'], ['problem', 'With an open problem']], 'state', 'Review state'),
                   select([['new', 'Newest first'], ['name', 'By name'], ['imp', 'Most built upon']], 'sort', 'Order'), q);
    const count = el('p', 'faint small count'), cards = el('div', 'cards'), moreBox = el('div', 'more-box');
    function draw() {
      let list = rows.filter(r => (st.what === 'all' || r.what === st.what) && (!st.area || r.area === st.area) &&
        (!st.state || rowState(r) === st.state || (st.state === 'problem' && rowState(r) === 'disputed')) &&
        (!st.q || (r.name + ' ' + r.decl + ' ' + r.text).toLowerCase().includes(st.q)));
      if (st.sort === 'name') list = [...list].sort((a, b) => a.name.localeCompare(b.name));
      if (st.sort === 'imp') list = [...list].sort((a, b) => b.imp - a.imp);
      count.textContent = `${plural(list.length, 'declaration')}`;
      cards.replaceChildren(...list.slice(0, st.shown).map(namedCard));
      moreBox.replaceChildren();
      if (list.length > st.shown) {
        const b = el('button', 'btn', `Show ${Math.min(60, list.length - st.shown)} more`);
        b.type = 'button';
        b.addEventListener('click', () => { st.shown += 60; draw(); });
        moreBox.append(b);
      }
    }
    draw();
    show(head, filters, count, cards, moreBox);
  };

  function namedCard(r) {
    const card = el('article', 'card');
    const state = rowState(r);
    card.append(glyph(r.what === 'result' ? 'theorem' : 'definition', state, {size: 30, named: true}));
    const body = el('div', 'card-body');
    const title = link(URLS.decl(r.decl), plain(r.name), 'card-title stretched');
    body.append(title, mdInline(r.text, 'card-text'));
    const metaLine = el('div', 'card-meta');
    metaLine.append(el('span', 'mono', r.decl));
    const facts = el('div', 'card-facts');
    facts.append(el('span', 'chip', r.area));
    const reviews = r.people || r.ai ? [r.people ? plural(r.people, 'person', 'people') : '', r.ai ? `${r.ai} AI` : ''].filter(Boolean).join(' · ') : 'not reviewed yet';
    facts.append(el('span', 'chip state-' + state, reviews));
    const [members, people, withAi, problems] = r.cov;
    if (members > 1) facts.append(coverageBar(members, people, withAi, problems));
    facts.append(el('span', 'faint', date(r.at)));
    body.append(metaLine, facts);
    card.append(body);
    return card;
  }
  /* What a named declaration rests on in Tau Ceti, and how much of it is reviewed. */
  function coverageBar(members, people, withAi, problems) {
    const wrap = el('span', 'cov'), bar = el('span', 'bar');
    const part = (n, cls) => { if (n > 0) { const i = el('i', cls); i.style.width = (100 * n / members).toFixed(1) + '%'; bar.append(i); } };
    const counted = ai ? withAi : people;
    part(counted, 'b-done'); part(ai ? 0 : withAi - people, 'b-ai'); part(problems, 'b-problem');
    wrap.append(bar, el('span', 'faint', `${counted}/${members}`));
    wrap.title = `Rests on ${plural(members, 'declaration')} of Tau Ceti: ${people} reviewed by people` +
      (withAi > people ? `, ${withAi - people} more by AI agents only` : '') + (problems ? `, ${problems} with an open problem` : '');
    return wrap;
  }

  VIEWS.decl = async (name, gen) => {
    const [meta, d, named] = await Promise.all([TauData.meta(), TauData.decl(name), TauData.named()]);
    if (gen !== generation) return;
    if (!d) return VIEWS.missing(name, gen, 'No declaration of that name is in this build.');
    const n = d.node, project = !!(n.flags & FLAG.PROJECT);
    const up = project ? {} : ((await TauData.upstream())[name] || {});
    const e = d.entry || up;
    const row = named.find(r => r.decl === name);
    const modName = d.module ? d.module.name : ((await TauData.modules())[n.mod] || [''])[0];
    if (gen !== generation) return;
    setContext(project ? [...await moduleTrail(modName), [shortName(name), null]] : [['Outside ' + meta.library.name, null], [name, null]]);
    const wrap = el('div', 'decl'), main = el('div', 'decl-main'), panel = el('aside', 'panel');
    // Head.
    const kind = el('div', 'kind');
    kind.append(glyph(n.kind, stateOf(n), {size: 26, named: !!row, upstream: !project}), kindWord[n.kind] || 'Declaration');
    if (row) {
      kind.append(el('span', 'sep', '·'), 'announced by Voyager ' + date(row.at));
      row.prs.forEach(p => { kind.append(' ', ext(`https://github.com/${meta.library.repo}/pull/${p}`, `#${p}`)); });
    }
    if (!project) kind.append(el('span', 'sep', '·'), modName.split('.')[0] === 'Mathlib' ? 'from Mathlib' : 'from ' + modName.split('.')[0]);
    const title = row ? row.name : (n.title || shortName(name));
    const leanName = el('div', 'decl-name');
    const copyName = el('button', 'btn small', 'Copy');
    copyName.type = 'button';
    copyName.addEventListener('click', async () => { try { await navigator.clipboard.writeText(name); copyName.textContent = 'Copied'; } catch (x) { /* ignore */ } });
    leanName.append(el('span', null, name), copyName);
    const links = el('div', 'links');
    if (project) {
      links.append(ext(URLS.docs(meta, name, modName), 'API docs'));
      if (e.line && d.module) links.append(ext(URLS.source(meta, d.module.path, e.line), 'Source'));
      if (row && row.post) links.append(ext(row.post, "Voyager's post"));
    } else {
      if (modName.startsWith('Mathlib')) links.append(ext(URLS.mathlib(name, modName), "Mathlib's docs"), ext(URLS.explorer(name), 'Mathlib Explorer'));
    }
    const h1 = el('h1');
    h1.append(mdInline(title));
    main.append(kind, h1, leanName, links);
    if (row && row.text) main.append(md(row.text, 'doc announce'));
    // The docstring, unless all it says is the title above.
    if (e.doc && (row || e.doc.trim() !== (n.title || '').trim())) main.append(md(e.doc, 'doc'));
    if (e.sig || e.stmt) {
      // What the docs show: the signature Lean prints, section variables included, its names linked; a
      // definition's value folded (the docs' Equations), a structure's fields; never a proof.
      const lean = el('div', 'lean');
      if (e.sig) lean.append(signature(e.kw, e.sig, e.sigRefs || [], e.sigNames || []));
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
      main.append(lean);
    }
    // The map, and the same as lists.
    const mapSec = el('section', 'block');
    mapSec.append(el('h2', null, 'What it rests on, and what rests on it'));
    if (row && row.cov[0] > 1) {
      const [members, people, withAi, problems] = row.cov, cov = el('div', 'coverage');
      cov.append(coverageBar(members, people, withAi, problems),
                 `Its meaning rests on ${plural(members, 'declaration')} of ${meta.library.name}: ${people} reviewed by people, ` +
                 `${withAi - people} only by AI agents, ${members - withAi - problems} by nobody` + (problems ? `, ${problems} with an open problem` : '') + '.');
      mapSec.append(cov);
    }
    const mapHost = el('div');
    if (project) { mapSec.append(mapHost); main.append(mapSec); }
    const lists = el('div', 'lists');
    const isResult = n.kind === 'theorem';
    if (project) lists.append(section(isResult ? 'What it is about' : 'What it is built from', await nodeList(n.m, n.nm, 'Nothing here.')));
    if (n.p.length || e.nRoutine) {
      const box = await nodeList(n.p, n.np, 'Only routine steps.');
      if (e.nRoutine) box.append(el('p', 'faint small', `and ${plural(e.nRoutine, 'routine step')} (arithmetic, logic and automation)`));
      lists.append(section(isResult ? 'How it is proved' : 'What the proofs in it use', box));
    }
    if (!project) lists.append(el('p', 'faint', `What it rests on is not followed outside ${meta.library.name}: Mathlib Explorer shows it.`));
    {
      if (e.builtOn) lists.append(section('Built on it', await nodeList(e.builtOn, e.nBuiltOn, '')));
      if (e.facts) lists.append(section('Results about it', await nodeList(e.facts, e.nFacts, '')));
      if (e.examples) lists.append(section('Examples', await nodeList(e.examples, e.nExamples, '')));
      if (e.usedIn) lists.append(section('Used to prove', await nodeList(e.usedIn, e.nUsedIn, '')));
    }
    main.append(lists);
    // The review panel.
    const records = project ? (e.records || []) : (up.records || []);
    if (gen !== generation) return;
    const people = records.filter(v => v.kind === 'review' && v.verdict === 'accept' && v.inForce && v.applies && v.by.kind !== 'agent').length;
    const agents = records.filter(v => v.kind === 'review' && v.verdict === 'accept' && v.inForce && v.applies && v.by.kind === 'agent').length;
    panel.append(el('h2', 'panel-title', 'Review'));
    const stateLine = el('div', 'state-line');
    stateLine.append(glyph(n.kind, stateOf(n), {size: 30, named: !!row, upstream: !project}));
    const words = el('div');
    words.append(el('div', 'state-text', STATE_TEXT[stateOf(n)]),
                 el('div', 'faint small', people || agents ? `Reviewed-by · ${plural(people, 'person', 'people')} · ${agents} AI`
                   : records.some(v => v.kind === 'review' && v.verdict === 'accept') ? 'No review of this version yet.' : 'Nobody has reviewed it yet.'));
    stateLine.append(words);
    panel.append(stateLine);
    if (project) {
      panel.append(ext(URLS.docs(meta, name, modName), 'Read it in the API docs ↗', 'btn docs-btn'));
      const actions = el('div', 'actions');
      FORMS.forEach(([text, template, prefix, cls]) => actions.append(ext(URLS.form(meta, template, prefix, name), text, 'btn ' + cls)));
      panel.append(actions, el('p', 'faint small', 'Each opens a form on GitHub, filled in. Recorded under your account within minutes.'));
    } else if (records.length) {
      panel.append(el('p', 'faint small', `Reviews of ${name} are kept in the stores that review it; they show here as they are.`));
    } else {
      panel.append(el('p', 'faint small', `Outside ${meta.library.name}: review it where it lives, such as the Mathlib probability store.`));
    }
    const byId = new Map(records.map(v => [v.id, v]));
    // Tests are listed below with whether they pass; Voyager's announcement heads the page.
    const top = records.filter(v => v.kind !== 'comment' && v.kind !== 'test' && !(v.kind === 'named' && v.by.agent && v.by.agent.tool === 'Voyager'));
    const order = v => (v.inForce && v.applies !== false ? 0 : 1);
    top.sort((a, b) => order(a) - order(b) || (b.at || '').localeCompare(a.at || ''));
    if (top.length) top.forEach(v => panel.append(thread(v, byId)));
    if ((e.tests || []).length) {
      const t = el('div', 'tests');
      t.append(el('h3', null, 'Tests'));
      e.tests.forEach(x => {
        const line = el('div', 'test-line');
        line.append(el('span', 'result ' + x.result, {passes: 'passes', sorry: 'with sorry', missing: 'missing'}[x.result]),
                    link(URLS.decl(x.test), shortName(x.test), 'mono'));
        if (x.text) line.append(' — ', mdInline(x.text));
        const by = el('div', 'faint small');
        by.append(x.challenge ? 'Suggested, and met; listed by ' : 'Listed by ', who(x.by), ' · ' + date(x.at));
        if (x.url) by.append(' · ', ext(x.url, 'issue'));
        line.append(by);
        t.append(line);
      });
      panel.append(t);
    }
    wrap.append(main, panel);
    show(wrap);
    if (project) TauMap.draw(mapHost, n, d.entry, {ai: () => ai});
  };

  VIEWS.module = async (name, gen) => {
    const [meta, found] = await Promise.all([TauData.meta(), TauData.moduleByName(name)]);
    if (gen !== generation) return;
    if (!found || !found.file) return VIEWS.missing(name, gen, 'No module of that name is in this build.');
    setContext(await moduleTrail(name));
    const f = found.file, head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Module'), el('h1', null, f.title || name), el('div', 'decl-name', name));
    const links = el('div', 'links');
    links.append(ext(URLS.source(meta, f.path, null), 'Source'));
    head.append(links);
    if (f.doc) head.append(md(f.doc, 'doc'));
    const ids = f.decls.map(x => x.id), items = await TauData.nodes(ids);
    if (gen !== generation) return;
    items.sort((a, b) => ((b.flags & FLAG.NAMED) - (a.flags & FLAG.NAMED)));
    const list = el('div', 'nlist');
    items.filter(x => !(x.flags & FLAG.AUX)).forEach(x => list.append(nodeItem(x)));
    show(head, section(plural(items.length, 'declaration'), list));
  };

  VIEWS.area = async (area, gen) => {
    const [meta, modules, named] = await Promise.all([TauData.meta(), TauData.modules(), TauData.named()]);
    if (gen !== generation) return;
    setContext([[meta.library.name, '#/browse'], [area, null]]);
    const mine = modules.slice(0, meta.counts.modules).map((m, i) => [m, i]).filter(([m]) => areaOf(m[0]) === area);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Area'), el('h1', null, area));
    const ns = named.filter(r => r.area === area), cards = el('div', 'cards');
    ns.slice(0, 24).forEach(r => cards.append(namedCard(r)));
    const list = el('div', 'mlist');
    mine.forEach(([m]) => {
      const a = link('#/m/' + encodeURIComponent(m[0]), null, 'mitem');
      a.append(el('span', 't', m[2] || m[0].split('.').slice(2).join('.') || m[0]), el('span', 'n', m[0]));
      list.append(a);
    });
    show(head, ns.length ? section(`Named here (${ns.length})`, cards) : el('div'), section(plural(mine.length, 'module'), list));
  };

  VIEWS.browse = async (arg, gen) => {
    const meta = await TauData.meta();
    if (gen !== generation) return;
    setContext([[meta.library.name, null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Browse'), el('h1', null, `${meta.library.name}, area by area`));
    head.append(el('p', 'lede', `${plural(meta.counts.declarations, 'declaration')} in ${plural(meta.counts.modules, 'module')}, at ${meta.library.commit.slice(0, 7)}.`));
    const grid = el('div', 'areas');
    meta.areas.forEach(([a, n, k]) => {
      const t = link('#/area/' + encodeURIComponent(a), null, 'area-tile');
      t.append(el('b', null, a), el('span', null, `${plural(n, 'declaration')}${k ? ` · ${k} named` : ''}`));
      grid.append(t);
    });
    show(head, grid);
  };

  let searchGen = 0;
  VIEWS.search = async (q, gen) => {
    setContext([['Search', null]]);
    $('q').value = q;
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Search'), el('h1', null, q ? `“${q}”` : 'Search'));
    const status = el('p', 'faint small', 'Searching…'), list = el('div', 'nlist');
    show(head, status, list);
    if (!q.trim()) { status.textContent = 'Type a name, part of one, or words from a docstring.'; return; }
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
    const render = extra => {
      const all = hits.concat(extra).sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 200);
      status.textContent = all.length ? `${plural(hits.length + extra.length, 'match', 'matches')}${hits.length + extra.length > 200 ? ', the first 200' : ''}` : 'Nothing found yet…';
      return TauData.nodes([]).then(() => Promise.all(all.map(h => TauData.idOf(rows[h[2]][0]))))
        .then(ids => TauData.nodes(ids.filter(x => x != null)))
        .then(ns => { if (mine === searchGen) list.replaceChildren(...ns.sort((a, b) => ((b.flags & FLAG.NAMED) - (a.flags & FLAG.NAMED))).map(nodeItem)); });
    };
    await render([]);
    const titles = await TauData.titles();
    if (gen !== generation || mine !== searchGen) return;
    const extra = [];
    const seen = new Set(hits.map(h => h[2]));
    titles.forEach((t, i) => { if (!seen.has(i) && t && words.every(w => t.toLowerCase().includes(w))) extra.push([5, t.length, i]); });
    await render(extra);
    if (!hits.length && !extra.length) status.textContent = 'Nothing matches.';
  };

  VIEWS.activity = async (arg, gen) => {
    const [meta, act] = await Promise.all([TauData.meta(), TauData.activity()]);
    if (gen !== generation) return;
    setContext([['Activity', null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Activity'), el('h1', null, 'Reviews, problems and suggested tests'));
    const recordList = (vs, empty) => {
      if (!vs.length) return el('p', 'faint', empty);
      const box = el('div', 'records');
      const byId = new Map(vs.map(v => [v.id, v]));
      vs.forEach(v => { const t = thread(v, byId); t.prepend(link(URLS.decl(v.decl), v.decl, 'mono small decl-link')); box.append(t); });
      return box;
    };
    const queueIds = act.queue.map(q => q[0]);
    const weights = new Map(act.queue);
    const queueBox = el('div', 'nlist');
    (await TauData.nodes(queueIds)).forEach(x => { const item = nodeItem(x); item.append(el('span', 'weight', `${plural(weights.get(x.id), 'named result')} ${weights.get(x.id) === 1 ? 'rests' : 'rest'} on it`)); queueBox.append(item); });
    const reviewers = el('div', 'reviewers');
    act.reviewers.forEach(r => reviewers.append(el('span', 'chip' + (r.kind === 'agent' ? ' agent' : ''), `${r.label} · ${r.n}`)));
    show(head,
      section('Open problems', recordList(act.problems, 'No open problems.')),
      section('Open questions', recordList(act.questions, 'No open questions.')),
      section('Suggested tests, still open', recordList(act.challenges, 'No open suggestions.')),
      section('What to review next', el('p', 'faint small', 'Unreviewed declarations of Tau Ceti that named results rest on, those most of them share first.'), queueBox),
      section('Latest', recordList(act.recent, 'Nothing yet.')),
      section('Reviewers', act.reviewers.length ? reviewers : el('p', 'faint', 'Nobody yet.')));
  };

  VIEWS.help = async (arg, gen) => {
    const meta = await TauData.meta();
    if (gen !== generation) return;
    setContext([['How to review', null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'How to review'), el('h1', null, 'Leave a review, a problem, a test or a question'));
    const p = (...parts) => { const x = el('p', 'prose'); x.append(...parts); return x; };
    const code = t => { const c = el('pre', 'small-code'); c.textContent = t; return c; };
    show(head,
      p('Open a declaration and use its buttons: each opens a form on GitHub, filled in with the declaration and the commit this page shows. ',
        'Submit it, and the record is kept in this site\'s evidence store under your GitHub account, and shown here within minutes. No pull request.'),
      section('What each form records',
        p(el('b', null, 'Review this'), ': it is the intended mathematical notion, or states the intended result. Say what you compared it with and which ways it could go wrong you checked. A person need not say why; an AI agent must.'),
        p(el('b', null, 'Report a problem'), ': it is wrong, and why. The problem stays open, and the declaration is flagged, until someone marks it fixed, intended, or not a problem.'),
        p(el('b', null, 'Suggest a test'), ': a property it should have, in words and if you can in Lean. It stays open until a declaration of Tau Ceti proves it.'),
        p(el('b', null, 'List a test'), ': a declaration of Tau Ceti that already pins it down, and what it checks.'),
        p(el('b', null, 'Ask a question'), ': anything you want its authors or reviewers to answer.')),
      section('Versions',
        p('A review is pinned to the declaration as it was: to its meaning hash, which changes when the declaration changes or anything it rests on does. ',
          'A review of an earlier version stays, greyed: "the declaration has changed since", or "something it rests on has changed since". Nothing is written into Tau Ceti.')),
      section('Many at once, and AI agents',
        p('Comment lines like these on ', ext(URLS.bulk(meta), `issue #${meta.store.bulk}`), ', one record each:'),
        code('Reviewed-by: TauCeti.Foo.bar — what you checked\nTest: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — its value at 0\nChallenge: TauCeti.Foo.bar — it is additive\nNamed: TauCeti.Foo.bar — The bar theorem — a sentence'),
        p('An AI agent names itself in its comment, and its records are shown apart from people\'s:'),
        code('<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->')),
      section('On a record\'s issue',
        p('A comment whose first line is a command changes its state: ', el('code', null, '/withdraw'), ', ', el('code', null, '/fixed'), ', ',
          el('code', null, '/intended'), ', ', el('code', null, '/invalid'), ', ', el('code', null, '/met <declaration>'), ', ',
          el('code', null, '/declined'), ', ', el('code', null, '/answered'), ', ', el('code', null, '/reopen'), '.')),
      section('Where this comes from',
        p('Built with the ', ext('https://github.com/LeanTrustBuilders', 'LeanTrustBuilders'), ' tools: the dataset of Tau Ceti at ',
          ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, meta.library.commit.slice(0, 7)),
          ` (${meta.dataset.producer}), the evidence store `, ext(`https://github.com/${meta.store.repo}`, meta.store.repo),
          meta.imports.length ? ', and the stores it imports: ' : '.', ...meta.imports.flatMap((s, i) => [i ? ', ' : '', ext(`https://github.com/${s.repo}`, s.name)]))));
  };

  VIEWS.missing = async (what, gen, why) => {
    setContext([['Not found', null]]);
    const head = el('div', 'page-head');
    head.append(el('h1', null, 'Not here'), el('p', 'lede', why || 'There is no page at this address.'));
    if (what) head.append(link('#/search/' + encodeURIComponent(String(what).split('.').pop()), 'Search for it'));
    show(head);
  };

  /* --- the rail ------------------------------------------------------------------------------------- */
  async function rail() {
    const [meta, named, act] = await Promise.all([TauData.meta(), TauData.named(), TauData.activity()]);
    const nav = $('rail-nav');
    const item = (href, text, count) => { const a = link(href, null, 'nav-item'); a.append(el('span', null, text), el('small', null, count)); return a; };
    nav.replaceChildren(item('#/', 'Named results and definitions', named.length.toLocaleString('en')),
                        item('#/activity', 'Open problems', act.problems.length), item('#/activity', 'Suggested tests', act.challenges.length),
                        item('#/activity', 'Recent reviews', act.recent.filter(v => v.kind === 'review').length));
    $('rail-areas').replaceChildren(...meta.areas.map(([a, n]) => item('#/area/' + encodeURIComponent(a), a, n.toLocaleString('en'))));
    $('rail-foot').replaceChildren(`${meta.library.name} at `,
      ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, meta.library.commit.slice(0, 7)),
      meta.library.date ? ` (${date(meta.library.date)})` : '', el('br'), `Built ${date(meta.built)} · `, link('#/help', 'about'));
    const pin = $('pin');
    pin.replaceChildren(ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, `${meta.library.name} @ ${meta.library.commit.slice(0, 7)}`));
    $('store-link').href = `https://github.com/${meta.store.repo}`;
  }

  /* --- wiring --------------------------------------------------------------------------------------- */
  async function route() {
    const r = parse(location.hash);
    if (location.hash && !location.hash.startsWith('#/') && r[0] !== 'missing') history.replaceState(null, '', address(r));
    current = r.join(':');
    document.body.classList.remove('rail-open');
    $('rail-toggle').setAttribute('aria-expanded', 'false');
    setNav({named: 'named', browse: 'browse', area: 'browse', module: 'browse', activity: 'activity', help: 'help'}[r[0]] || '');
    const gen = ++generation;
    ready = false;
    try {
      await VIEWS[r[0]](r[1], gen);
    } catch (e) {
      if (gen === generation) {
        const box = el('div', 'page-head');
        box.append(el('h1', null, 'This page could not be shown'), el('pre', 'small-code', String(e && e.stack || e)));
        show(box);
      }
      console.error(e);
    }
    if (gen === generation) ready = true;
  }
  let typing = null;
  $('q').addEventListener('input', e => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      const target = '#/search/' + encodeURIComponent(e.target.value);
      if (location.hash.startsWith('#/search/')) { history.replaceState(null, '', target); route(); } else location.hash = target;
    }, 250);
  });
  document.addEventListener('keydown', e => {
    if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))) {
      e.preventDefault(); $('q').focus(); $('q').select();
    }
  });
  const aiBox = $('ai');
  aiBox.checked = ai;
  aiBox.addEventListener('change', () => {
    ai = aiBox.checked;
    try { localStorage.setItem('tauceti-review:ai', ai ? '1' : '0'); } catch (e) { /* not kept */ }
    route();
  });
  $('rail-toggle').addEventListener('click', () => {
    const open = document.body.classList.toggle('rail-open');
    $('rail-toggle').setAttribute('aria-expanded', String(open));
  });
  window.addEventListener('hashchange', route);
  rail().catch(e => console.error(e));
  route();

  /* For the browser check (tests/validate_site.py). */
  window.TauReview = Object.freeze({
    get ready() { return ready; },
    route: () => current,
    mapNodes: () => [...document.querySelectorAll('.map .node[data-name]')].map(g => g.dataset.name),
    fnv: TauData.fnv,
  });
})();
