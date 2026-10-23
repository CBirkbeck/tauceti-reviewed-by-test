/* Tau Ceti Review: how things look. Elements, Markdown (the Atlas's TauMarkdown: source HTML stays
   text, mathematics becomes vetted MathML), kinds and review states as Mathlib Explorer marks them
   (a pill for the kind, a badge for the state), and links. */
(function () {
  'use strict';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function link(href, text, cls) { const a = el('a', cls, text); a.href = href; return a; }
  function ext(href, text, cls) { const a = link(href, text, cls); a.target = '_blank'; a.rel = 'noopener'; return a; }
  /* Markdown from a docstring or a record: always through TauMarkdown, never as HTML. */
  function md(text, cls) {
    const box = el('div', 'md' + (cls ? ' ' + cls : ''));
    box.append(window.TauMarkdown.render(text || ''));
    return box;
  }
  /* One paragraph's content, for a line of text. Inside a link (`bare`), its own links become text. */
  function mdInline(text, cls, bare) {
    const frag = window.TauMarkdown.render(text || ''), span = el('span', 'md' + (cls ? ' ' + cls : ''));
    if (frag.childNodes.length === 1 && frag.firstChild.nodeName === 'P') {
      while (frag.firstChild.firstChild) span.append(frag.firstChild.firstChild);
    } else span.append(frag);
    if (bare) span.querySelectorAll('a').forEach(a => a.replaceWith(...a.childNodes));
    return span;
  }

  /* A kind is a colour: a notion blue, a result green, an instance purple (Mathlib Explorer's). */
  const KIND_WORD = {theorem: 'Theorem', definition: 'Definition', structure: 'Structure', class: 'Class',
                     inductive: 'Inductive type', instance: 'Instance', axiom: 'Axiom', opaque: 'Definition'};
  const kindClass = kind => ({theorem: 'result', axiom: 'result', instance: 'instance'})[kind] || 'concept';
  const kindPill = (kind, word) => el('span', 'kind ' + kindClass(kind), word || KIND_WORD[kind] || 'Declaration');
  /* A review state is a badge: a dot in its colour and a word. */
  const STATE_TEXT = {unreviewed: 'Not reviewed yet', covered: 'Reviewed', uncounted: 'Reviewed, by AI agents only',
                      stale: 'Reviewed on an earlier version', problem: 'An open problem', disputed: 'Reviewed, with an open problem'};
  const STATE_SHORT = {unreviewed: 'Not reviewed', covered: 'Reviewed', uncounted: 'AI only', stale: 'Earlier version',
                       problem: 'Problem', disputed: 'Disputed'};
  function stateBadge(state, long) {
    const s = el('span', 'st st-' + state);
    s.append(el('i'), (long ? STATE_TEXT : STATE_SHORT)[state] || state);
    s.title = STATE_TEXT[state] || state;
    return s;
  }

  const modulePath = mod => mod.split('.').join('/');
  const anchor = name => encodeURIComponent(name);
  const URLS = {
    docs: (meta, name, mod) => `${meta.library.docs}/${modulePath(mod)}.html#${anchor(name)}`,
    source: (meta, path, line) => `https://github.com/${meta.library.repo}/blob/${meta.library.commit}/${path}` +
      (line ? `#L${line[0]}-L${line[1]}` : ''),
    mathlib: (name, mod) => `https://leanprover-community.github.io/mathlib4_docs/${modulePath(mod)}.html#${anchor(name)}`,
    explorer: name => `https://leantrustbuilders.github.io/mathlib-explorer/#/d/${anchor(name)}`,
    github: login => `https://github.com/${encodeURIComponent(login)}`,
    issues: meta => `https://github.com/${meta.store.repo}/issues`,
    bulk: meta => `https://github.com/${meta.store.repo}/issues/${meta.store.bulk}`,
    form: (meta, template, title, name) => `https://github.com/${meta.store.repo}/issues/new?` +
      new URLSearchParams({template, title: title + name, decl: name, commit: meta.library.commit}).toString(),
    decl: name => '#/d/' + encodeURIComponent(name),
  };
  /* The forms a person fills in from the review box: [its template, its issue title before the name]. */
  const FORMS = {
    review: ['evidence-review.yml', 'Review: '],
    problem: ['evidence-problem.yml', 'Problem: '],
    challenge: ['evidence-challenge.yml', 'Challenge: '],
    question: ['evidence-question.yml', 'Question: '],
  };

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function date(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso : `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }
  const plural = (n, one, many = one + 's') => `${Number(n).toLocaleString('en')} ${n === 1 ? one : many}`;
  /* Who made a record: a person's account, or the AI agent and the account it acted through. */
  function who(by) {
    const span = el('span', 'who');
    if (by.kind === 'agent') {
      const a = by.agent || {};
      span.append(el('span', 'ai', 'AI'), ' · ' + [a.tool || 'agent', a.model].filter(Boolean).join(' · '));
      if (by.login) span.append(' via ', ext(URLS.github(by.login), by.login));
    } else if (by.login) span.append(ext(URLS.github(by.login), by.login));
    else span.append(by.label || 'someone');
    return span;
  }
  /* A docstring's first sentence as plain text, for a label: its Markdown marks dropped. */
  const plain = text => String(text || '').replace(/\*\*|__|`/g, '').replace(/(^|[^\w])[*_]([^*_]+)[*_](?!\w)/g, '$1$2')
    .replace(/\$\$?([^$]+)\$\$?/g, '$1').trim();
  /* A declaration's last name component, or the last two when the last is short. */
  function shortName(name) {
    const parts = name.split('.');
    let k = parts.length - 1;
    while (k > 0 && /^[a-z_]/.test(parts[k]) === false && parts[k].length < 3) k--;
    return parts.slice(k).join('.');
  }

  window.TauRender = Object.freeze({el, link, ext, md, mdInline, kindClass, kindPill, KIND_WORD, stateBadge, STATE_TEXT,
                                    URLS, FORMS, date, plural, who, shortName, modulePath, plain});
})();
