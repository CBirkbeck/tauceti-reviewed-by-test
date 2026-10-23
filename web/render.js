/* Tau Ceti Review: how things look. Elements, Markdown (the Atlas's TauMarkdown: source HTML stays
   text, mathematics becomes vetted MathML), the Atlas's planets ringed by review state, and links. */
(function () {
  'use strict';
  const SVGNS = 'http://www.w3.org/2000/svg';

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
  /* One paragraph's content, for a line of text. */
  function mdInline(text, cls) {
    const frag = window.TauMarkdown.render(text || ''), span = el('span', 'md' + (cls ? ' ' + cls : ''));
    if (frag.childNodes.length === 1 && frag.firstChild.nodeName === 'P') {
      while (frag.firstChild.firstChild) span.append(frag.firstChild.firstChild);
    } else span.append(frag);
    return span;
  }

  /* The Atlas's planets (tauceti-explorer, src/graph.js): a definition is an Earth, a theorem a Saturn;
     an instance here is a small grey moon. Colour round them means review state, and nothing else. */
  const OCEAN = '#6f9fcf', LAND = '#9cc59a', SAND = '#d9c391', RING = '#ece0bf', MOON = '#8a96a3', ACCENT = '#dfc186';
  const LAND_PATH = 'M-.55,-.35Q-.3,-.75 .05,-.55Q.3,-.4 .1,-.15Q-.1,.05 -.35,-.05Q-.7,0 -.55,-.35Z' +
    'M.2,.25Q.55,.1 .65,.35Q.6,.65 .3,.7Q.05,.6 .2,.25Z';
  const ringArc = (r, near) => `M${-1.75 * r},0A${1.75 * r},${.42 * r} 0 0,${near ? 0 : 1} ${1.75 * r},0`;
  const STATE_RING = {unreviewed: '#5b6875', covered: '#f7f3e9', uncounted: '#e89678', stale: '#e89678',
                      problem: '#d4604c', disputed: '#d4604c'};
  const STATE_TEXT = {unreviewed: 'Not reviewed yet', covered: 'Reviewed', uncounted: 'Reviewed, by AI agents only',
                      stale: 'Reviewed on an earlier version', problem: 'An open problem', disputed: 'Reviewed, with an open problem'};
  function planetMarkup(kind, r) {
    if (kind === 'instance') return `<circle r="${(r * .72).toFixed(2)}" fill="${MOON}"/>`;
    if (kind === 'theorem' || kind === 'axiom') {
      const ring = near => `<path d="${ringArc(r, near)}" fill="none" stroke="${RING}" stroke-width="1.1" transform="rotate(-18)"/>`;
      return ring(false) + `<circle r="${r}" fill="${SAND}"/>` + ring(true);
    }
    return `<circle r="${r}" fill="${OCEAN}"/><path d="${LAND_PATH}" fill="${LAND}" transform="scale(${r})"/>`;
  }
  /* The planet with its review ring, its gold ring when named, and a sun mark when it is Mathlib's. */
  function glyphMarkup(kind, state, o) {
    const r = o.r, R = r * 1.7;
    let s = '';
    if (o.named) s += `<circle r="${(R + 3).toFixed(2)}" fill="none" stroke="${ACCENT}" stroke-width="1.2"/>`;
    s += `<circle r="${R.toFixed(2)}" fill="none" stroke="${STATE_RING[state] || STATE_RING.unreviewed}" ` +
         `stroke-width="${state === 'unreviewed' ? 1 : 1.7}"${state === 'stale' ? ' stroke-dasharray="2 2"' : ''}/>`;
    if (state === 'disputed') s += `<circle r="${(R - 2).toFixed(2)}" fill="none" stroke="#f7f3e9" stroke-width="1"/>`;
    s += `<g${o.upstream ? ' opacity=".55"' : ''}>${planetMarkup(kind, r)}</g>`;
    if (o.upstream) s += `<circle cx="${(r * 1.25).toFixed(2)}" cy="${(-r * 1.25).toFixed(2)}" r="${Math.max(1.7, r * .34).toFixed(2)}" fill="${ACCENT}"/>`;
    return s;
  }
  function glyph(kind, state, o = {}) {
    const size = o.size || 22, svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('class', 'glyph');
    svg.setAttribute('width', size); svg.setAttribute('height', size);
    svg.setAttribute('viewBox', `${-size / 2} ${-size / 2} ${size} ${size}`);
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = glyphMarkup(kind, state, {...o, r: size / 2 / (o.named ? 2.6 : 2.15)}); // constants only
    return svg;
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
  const FORMS = [
    ['Review this', 'evidence-review.yml', 'Review: ', 'primary'],
    ['Report a problem', 'evidence-problem.yml', 'Problem: ', ''],
    ['Suggest a test', 'evidence-challenge.yml', 'Challenge: ', ''],
    ['List a test', 'evidence-test.yml', 'Test: ', ''],
    ['Ask a question', 'evidence-question.yml', 'Question: ', ''],
  ];

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
  /* A docstring's first sentence as plain text, for a link or a label: its Markdown marks dropped. */
  const plain = text => String(text || '').replace(/\*\*|__|`/g, '').replace(/(^|[^\w])[*_]([^*_]+)[*_](?!\w)/g, '$1$2')
    .replace(/\$\$?([^$]+)\$\$?/g, '$1').trim();
  /* A declaration's last name component, or its title when that is short. */
  function shortName(name) {
    const parts = name.split('.');
    let k = parts.length - 1;
    while (k > 0 && /^[a-z_]/.test(parts[k]) === false && parts[k].length < 3) k--;
    return parts.slice(k).join('.');
  }

  window.TauRender = Object.freeze({el, link, ext, md, mdInline, glyph, glyphMarkup, planetMarkup, STATE_TEXT, STATE_RING,
                                    URLS, FORMS, date, plural, who, shortName, modulePath, plain});
})();
