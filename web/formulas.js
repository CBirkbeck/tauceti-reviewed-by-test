/* Tau Ceti Review: formulas written as text, typeset. Tau Ceti's docstrings and Voyager's sentences write
   mathematics in Unicode with TeX's marks, `Θ_L(τ) = ∑_{v ∈ L} exp (π i ‖v‖² τ)`, and Markdown would read
   their underscores as emphasis. A formula with a subscript or a superscript, in a code span or as a run
   of symbols in a sentence, becomes $…$, which TauMarkdown typesets with KaTeX. Lean stays as it is (a
   dotted name, a typing `x : T`, a word no formula holds), and so does what KaTeX cannot read; an
   underscore left in a sentence is kept from reading as emphasis. */
(function () {
  'use strict';

  // The words a formula may hold: TeX's operators, and more set upright.
  const OPS = new Set(('arccos arcsin arctan arg cos cosh cot coth csc deg det dim exp gcd hom inf ker lg lim liminf ' +
                       'limsup ln log max min sec sin sinh sup tan tanh').split(' '));
  const UPRIGHT = new Set(('Ad ad Aut Br card Cl conj Der Div End erf Ext Fix Frac Frob Gal gl GSp Hom im Im Ind Ker lcm Li ' +
                           'Lie Mat mod ord Pic Pin Proj PSp rank re Re Res res sgn sl Sp span Spec Spin Stab supp Sym Tor tr Tr ' +
                           'vol').split(' '));
  // Short words that are English, not a product of variables.
  const ENGLISH = new Set(('an and any are as at be but by can cf do eg end etc for has how ie if in is it its let may new no ' +
                           'nor not of off on one or out per see set so the to too two up use via vs we who why').split(' '));
  /* Whether some word of `s` is one no formula holds: a long word not an operator's, a short English one,
     or a short one on its own; xy, Du and SL pass beside a symbol, as in exp(tx), ‖Du‖_p and SL₂(ℤ). */
  const foreign = s => s.split(/\s+/).some(w => (w.match(/[A-Za-z]{2,}/g) || []).some(r => !OPS.has(r) && !UPRIGHT.has(r) &&
    (r.length > 3 || ENGLISH.has(r.toLowerCase()) || /^[A-Za-z]+$/.test(w.replace(/[.,;:!?]+$/, '')))));
  // A subscript or a superscript, as TeX writes them (Θ_L, x_i, ∑_{v ∈ L}, x^2) or as Unicode does (‖v‖², ℝⁿ, x₀).
  const MARK = new RegExp(['[^\\x00-\\x7f)\\]}]_\\S', "(?:^|[^A-Za-z0-9_.'])[A-Za-z]_[\\p{L}\\p{N}](?![\\p{L}\\p{N}_])", '[_^]\\{',
                           '[\\p{L}\\p{N})\\]}|‖]\\^[\\p{L}\\p{N}({-]', '[⁰²³⁴⁵⁶⁷⁸⁹ⁿ₀-₉]'].join('|'), 'u');
  const MARKS = /[_^⁰²³⁴⁵⁶⁷⁸⁹ⁿ₀-₉]/;
  // Lean, not mathematics: a definition, a typing, a function, a tactic, a dotted name, and Lean's own
  // notation (ℚ_[p], f^[n], f '' s, f ⁻¹' s, →+*, ≃ₗ[R]).
  const LEAN = /:=|(?:^|\s):(?:\s|$)|\bfun\b|\bby\b|=>|\p{L}\.\p{L}|[_^]\[|\s''\s|⁻¹'|[→≃][+*ₗₐ]/u;
  // What a formula in a sentence is made of: letters, digits, mathematical signs and brackets.
  const SYMBOLIC = /^[\p{L}\p{N}\p{Sm}\p{Mn}()[\]{}⟨⟩⟪⟫⁅⁆|‖_^'·,.!…∘−\-/⁽⁾₍₎]+$/u;
  // A sign a formula does not end on, nor begin with.
  const OPERATOR = /^[=+\-−·×/⧸∘<>≤≥≠≈≡≅≃∼→←↦⟶⇒⇔↔∈∉⊂⊆⊃⊇∪∩∧∨⊗⊕•∣|]+$/u;
  const TABLE = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$/m;

  /* TeX for a formula: TeX's operators as commands, a name in capitals upright, braces that group nothing
     escaped, ‖ as \|, Σ and Π before limits or a term a sum and a product, and an exponent or an index as
     Lean writes them (x ^ (k - 2), x ^ 12, χ_Sym) grouped. KaTeX reads the rest of Unicode (Θ, ∑, ℍ, ≤, ², ⁻¹). */
  function tex(s) {
    const cps = Array.from(s), groups = [];
    let out = '';
    for (let i = 0; i < cps.length; i++) {
      const c = cps[i];
      if (c === '^' || c === '_') {
        let j = i + 1;
        while (cps[j] === ' ') j++;
        if (cps[j] === '(') {
          let depth = 0, k = j;
          for (; k < cps.length; k++) if (cps[k] === '(') depth++; else if (cps[k] === ')' && --depth === 0) break;
          if (k < cps.length) { out += c + '{' + tex(cps.slice(j + 1, k).join('')) + '}'; i = k; continue; }
        }
        const m = cps.slice(j, j + 12).join('').match(/^[-−]?(?:\d+|[A-Za-z](?![A-Za-z]))|^[A-Za-z]{2,}/);
        if (m && m[0].length > 1) { out += c + '{' + tex(m[0]) + '}'; i = j + m[0].length - 1; continue; }
        out += c;
      } else if (/[A-Za-z]/.test(c)) {
        let j = i;
        while (j < cps.length && /[A-Za-z]/.test(cps[j])) j++;
        const w = cps.slice(i, j).join('');
        out += w.length < 2 ? w : OPS.has(w) ? `\\${w} ` : UPRIGHT.has(w) ? `\\operatorname{${w}}` : /^[A-Z]+$/.test(w) ? `\\mathrm{${w}}` : w;
        i = j - 1;
      } else if (c === '{') {
        const grouping = /[_^]\s*$/.test(out);
        groups.push(grouping);
        out += grouping ? '{' : '\\{';
      } else if (c === '}') out += groups.length && groups.pop() ? '}' : '\\}';
      else if ((c === 'Σ' || c === 'Π') && /^[\s_^]/.test(cps[i + 1] || '')) out += c === 'Σ' ? '\\sum' : '\\prod';
      else if (c === '|' && cps[i - 1] === ' ' && cps[i + 1] === ' ') out += '\\mid';
      else if (c === '‖') out += '\\|';
      else if (c === '−') out += '-';
      else if (c === '~') out += '\\sim ';
      else if ('%#&'.includes(c)) out += '\\' + c;
      else out += c;
    }
    return out;
  }
  /* The TeX, if KaTeX reads it. */
  function readable(t) {
    try {
      window.katex.renderToString(t, {output: 'mathml', throwOnError: true, strict: 'ignore', maxExpand: 1000});
      return t;
    } catch (e) { return null; }
  }
  /* Whether every bracket is closed, and in order. */
  function balanced(s) {
    const open = [];
    for (const ch of s) {
      const o = '([{'.indexOf(ch), c = ')]}'.indexOf(ch);
      if (o >= 0) open.push(o);
      else if (c >= 0 && open.pop() !== c) return false;
    }
    return open.length === 0;
  }
  /* An underscore after a letter that is not ASCII starts emphasis in TauMarkdown; outside a formula, it is
     only an underscore. */
  const plainText = s => s.replace(/([^\x00-\x7f)\]}])_(?=\S)/gu, '$1\\_');
  /* A code span's text: its formula's TeX, or null to leave it code. */
  function inCode(s) {
    if (!MARK.test(s) || LEAN.test(s) || foreign(s) || /[$`\\]/.test(s)) return null;
    return readable(tex(s));
  }
  /* Words of a sentence that make a formula: as $…$ if there is a mark in them and their brackets close,
     the punctuation that ends the sentence and a bracket they do not open left outside. */
  function inWords(body) {
    const count = (s, c) => s.split(c).length - 1;
    let pre = '', post = (body.match(/[.,;:!?]+$/) || [''])[0];
    body = body.slice(0, body.length - post.length);
    while (body.endsWith(')') && count(body, ')') > count(body, '(')) { post = ')' + post; body = body.slice(0, -1); }
    while (body.startsWith('(') && count(body, '(') > count(body, ')')) { pre += '('; body = body.slice(1); }
    const t = MARK.test(body) && balanced(body) ? readable(tex(body)) : null;
    return pre + (t ? '$' + t + '$' : plainText(body)) + post;
  }
  /* A line of a sentence: each run of mathematical words in it, through inWords. A list's or a heading's
     mark is not mathematics, nor is an article beside a formula, nor a sign it ends on (`x² +` before `ax`);
     a run stops at the end of a clause. */
  function inLine(line, table) {
    if (table && line.includes('|')) return line;
    const lead = line.match(/^\s*(?:(?:[-+*]|\d+[.)]|#{1,6}|>)\s+)*/)[0];
    const parts = line.slice(lead.length).split(/(\s+)/), words = parts.filter((_, k) => k % 2 === 0);
    const mathy = words.map(w => {
      const core = w.replace(/[.,;:!?]+$/, '');
      if (/^[A-Za-z]{2,}$/.test(core) && !OPS.has(core)) return false;  // a word alone: `dim V`, not `Lie algebra`
      return core !== '' && SYMBOLIC.test(core) && !foreign(core) && !LEAN.test(core);
    });
    let out = lead;
    for (let k = 0; k < words.length;) {
      let a = k, b = k;
      while (mathy[k] && b + 1 < words.length && mathy[b + 1] && !/[.;:?]$/.test(words[b])) b++;
      const last = b;
      if (mathy[k]) {
        while (a <= b && (/^(?:a|A|I|[(,.;:!])$/.test(words[a]) || OPERATOR.test(words[a]))) a++;
        while (b >= a && (/^(?:a|A|I)$/.test(words[b]) || OPERATOR.test(words[b]))) b--;
      } else a = last + 1;
      for (let j = k; j <= last; j++) {
        if (j === a && a <= b) {
          out += inWords(words.slice(a, b + 1).map((w, i) => w + (a + i < b ? parts[2 * (a + i) + 1] : '')).join(''));
          j = b;
        } else out += plainText(words[j]);
        out += parts[2 * j + 1] || '';
      }
      k = last + 1;
    }
    return out;
  }
  /* Text outside fenced code: code spans and the rest, mathematics already marked and links left alone. */
  function inText(text, table) {
    let out = '', plain = '', i = 0;
    const flush = () => { out += plain.split('\n').map(l => inLine(l, table)).join('\n'); plain = ''; };
    while (i < text.length) {
      const delim = text.startsWith('\\(', i) ? ['\\(', '\\)'] : text.startsWith('\\[', i) ? ['\\[', '\\]']
        : text.startsWith('$$', i) ? ['$$', '$$'] : text[i] === '$' ? ['$', '$'] : null;
      const end = delim ? text.indexOf(delim[1], i + delim[0].length) : -1;
      if (end >= 0) { flush(); out += text.slice(i, end + delim[1].length); i = end + delim[1].length; continue; }
      if (text[i] === '\\') { plain += text.slice(i, i + 2); i += 2; continue; }
      if (text[i] === '`') {
        const ticks = text.slice(i).match(/^`+/)[0], close = text.indexOf(ticks, i + ticks.length);
        if (close < 0) { plain += ticks; i += ticks.length; continue; }
        flush();
        let content = text.slice(i + ticks.length, close).replace(/\n/g, ' ');
        if (/^ .* $/.test(content) && content.trim()) content = content.slice(1, -1);
        const t = inCode(content);
        out += t ? '$' + t + '$' : text.slice(i, close + ticks.length);
        i = close + ticks.length;
        continue;
      }
      const link = text[i] === '[' && text.slice(i).match(/^\[[^\]\n]*\]\([^)\n]*\)/);
      if (link) { flush(); out += link[0]; i += link[0].length; continue; }
      plain += text[i++];
    }
    flush();
    return out;
  }

  const cache = new Map();
  /* Markdown with its formulas marked as mathematics; fenced code as it is. */
  function typeset(text) {
    text = String(text || '');
    if (!MARKS.test(text) || !window.katex) return text;
    if (cache.has(text)) return cache.get(text);
    const table = TABLE.test(text), out = [];
    let fence = null, chunk = [];
    const flush = () => { if (chunk.length) out.push(inText(chunk.join('\n'), table)); chunk = []; };
    for (const line of text.split('\n')) {
      const f = line.match(/^ {0,3}(`{3,}|~{3,})/);
      if (fence) {
        out.push(line);
        if (f && f[1][0] === fence[0] && f[1].length >= fence.length && !line.slice(f[0].length).trim()) fence = null;
      } else if (f) { flush(); fence = f[1]; out.push(line); }
      else chunk.push(line);
    }
    flush();
    const result = out.join('\n');
    if (cache.size > 4000) cache.clear();
    cache.set(text, result);
    return result;
  }

  window.TauFormulas = Object.freeze({typeset});
})();
