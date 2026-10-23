/* Offline Markdown: source HTML stays text; optional mathematics uses vetted MathML. */
(function () {
  'use strict';

  const doc = window.document;
  const anchorTag = /^<a\s+(?:id|name)\s*=\s*(?:"([^"]*)"|'([^']*)')\s*>\s*<\/a\s*>/i;
  const fenceStart = /^ {0,3}(`{3,}|~{3,})(.*)$/;
  const listStart = /^([ \t]*)([-+*]|\d+[.)])\s+(.*)$/;
  const headingStart = /^ {0,3}(#{1,6})(?:\s+|$)(.*)$/;
  const mathNamespace = 'http://www.w3.org/1998/Math/MathML';
  const mathTags = new Set('math semantics annotation mrow mi mn mo mtext mspace mfrac msqrt mroot mstyle msub msup msubsup munderover munder mover mtable mtr mtd menclose mpadded mphantom mfenced mmultiscripts mprescripts none merror'.split(' '));
  const mathAttributes = new Set('display displaystyle scriptlevel mathvariant mathcolor mathbackground mathsize stretchy symmetric maxsize minsize fence separator accent accentunder largeop movablelimits lspace rspace linethickness bevelled numalign denomalign width height depth voffset columnalign rowalign columnspacing rowspacing columnlines rowlines frame framespacing equalrows equalcolumns columnspan rowspan notation encoding scriptminsize scriptsizemultiplier form'.split(' '));

  function renderedMath(source, formula, displayMode, options) {
    const fallback = () => doc.createTextNode(source);
    if ((options && options.renderMath === false) || !window.katex || typeof window.katex.renderToString !== 'function' || formula.length > 16000) return fallback();
    try {
      const markup = window.katex.renderToString(formula, {
        output: 'mathml', displayMode: !!displayMode, trust: false, throwOnError: false,
        strict: 'ignore', maxExpand: 1000, maxSize: 12, globalGroup: false
      });
      if (markup.length > 500000) return fallback();
      // XML parsing creates an inert tree. Only MathML names and presentation
      // attributes are copied: no source HTML, URLs, styles, or event handlers.
      const parsed = new window.DOMParser().parseFromString(markup, 'application/xml');
      if (parsed.getElementsByTagName('parsererror').length) return fallback();
      const root = parsed.getElementsByTagNameNS(mathNamespace, 'math')[0];
      if (!root) return fallback();
      let copied = 0;
      function copyMath(element, depth) {
        if (depth > 120 || ++copied > 20000) throw new Error('Formula is too complex.');
        if (element.nodeType === 3) return doc.createTextNode(element.nodeValue);
        if (element.nodeType !== 1 || element.namespaceURI !== mathNamespace || !mathTags.has(element.localName)) throw new Error('Unsupported MathML node.');
        const result = doc.createElementNS(mathNamespace, element.localName);
        Array.from(element.attributes).forEach(attribute => {
          if (!mathAttributes.has(attribute.name) || attribute.value.length > 400 || /[<>\u0000-\u001f]/.test(attribute.value)) return;
          result.setAttribute(attribute.name, attribute.value);
        });
        if (element.localName === 'annotation') result.textContent = element.textContent;
        else Array.from(element.childNodes).forEach(child => result.append(copyMath(child, depth + 1)));
        return result;
      }
      const wrapper = node('span');
      wrapper.className = displayMode ? 'md-math md-math-display' : 'md-math';
      wrapper.title = source;
      if (displayMode) {
        wrapper.style.display = 'block'; wrapper.style.overflowX = 'auto';
        wrapper.style.maxWidth = '100%'; wrapper.style.margin = '1em 0';
        wrapper.style.padding = '.3em 0';
      }
      wrapper.append(copyMath(root, 0));
      return wrapper;
    } catch (_) { return fallback(); }
  }

  function mathCloseAt(text, delimiter, start) {
    for (let index = start; index < text.length; index++) {
      if (!text.startsWith(delimiter, index)) continue;
      let slashes = 0;
      for (let previous = index - 1; previous >= 0 && text[previous] === '\\'; previous--) slashes++;
      if (slashes % 2 === 0) return index;
    }
    return -1;
  }

  function node(tag, text) {
    const element = doc.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function decodeEntities(text) {
    const named = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0'};
    return text.replace(/&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, function (all, value) {
      if (value[0] !== '#') return named[value.toLowerCase()] || all;
      const cp = value[1].toLowerCase() === 'x' ? parseInt(value.slice(2), 16) : parseInt(value.slice(1), 10);
      return cp > 0 && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) ? String.fromCodePoint(cp) : all;
    });
  }

  function slug(text) {
    return decodeEntities(String(text))
      .replace(/<[^>]*>/g, '')
      .replace(/!?\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/[`*_~]/g, '')
      .trim().toLowerCase()
      .replace(/[^\p{L}\p{N}\p{M}\s_-]/gu, '')
      .replace(/\s/g, '-');
  }

  function safeLink(raw) {
    const value = decodeEntities(raw).trim();
    // Browsers ignore several controls in URL schemes. Reject them before routing.
    if (!value || /[\u0000-\u001f\u007f]/.test(value) || value.includes('\\')) return null;
    if (/^https?:\/\//i.test(value) || value.startsWith('//')) {
      try {
        const url = new URL(value.startsWith('//') ? 'https:' + value : value);
        if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) return null;
        return {external: true, value: url.href};
      } catch (_) { return null; }
    }
    if (/^[^/?#]*:/.test(value)) return null;
    return {external: false, value};
  }

  function matchingBracket(text, start, open, close) {
    let depth = 1;
    for (let i = start + 1; i < text.length; i++) {
      if (text[i] === '\\') { i++; continue; }
      if (text[i] === open) depth++;
      if (text[i] === close && --depth === 0) return i;
    }
    return -1;
  }

  function linkAt(text, start) {
    const close = matchingBracket(text, start, '[', ']');
    if (close < 0 || text[close + 1] !== '(') return null;
    const end = matchingBracket(text, close + 1, '(', ')');
    if (end < 0) return null;
    let destination = text.slice(close + 2, end).trim();
    // Optional Markdown titles are display hints; they never become HTML.
    let title = '';
    const titled = destination.match(/^(.*?)\s+["']([^"']*)["']$/);
    if (titled) { destination = titled[1]; title = titled[2]; }
    if (destination.startsWith('<') && destination.endsWith('>')) destination = destination.slice(1, -1);
    destination = destination.replace(/\\([()])/g, '$1');
    return {label: text.slice(start + 1, close), destination, title, end: end + 1};
  }

  function inline(text, options, depth) {
    const out = doc.createDocumentFragment();
    if ((depth || 0) > 12) { out.append(doc.createTextNode(text)); return out; }
    let buffer = '';
    function flush() {
      if (buffer) { out.append(doc.createTextNode(decodeEntities(buffer))); buffer = ''; }
    }
    for (let i = 0; i < text.length;) {
      const rest = text.slice(i);
      const anchor = rest.match(anchorTag);
      if (anchor) {
        flush();
        const element = node('span');
        element.id = anchor[1] === undefined ? anchor[2] : anchor[1];
        element.className = 'md-anchor';
        out.append(element);
        i += anchor[0].length;
        continue;
      }
      const br = rest.match(/^<br\s*\/?\s*>/i) || rest.match(/^(?: {2,}|\\)\n/);
      if (br) { flush(); out.append(node('br')); i += br[0].length; continue; }
      // Preserve delimiters when the optional offline mathematics renderer is absent.
      const mathOpen = rest.startsWith('\\(') ? '\\(' : rest.startsWith('\\[') ? '\\[' : rest.startsWith('$$') ? '$$' : rest[0] === '$' ? '$' : null;
      if (mathOpen) {
        const mathClose = mathOpen === '\\(' ? '\\)' : mathOpen === '\\[' ? '\\]' : mathOpen;
        const end = mathCloseAt(text, mathClose, i + mathOpen.length);
        if (end >= 0) {
          flush();
          out.append(renderedMath(text.slice(i, end + mathClose.length), text.slice(i + mathOpen.length, end), mathOpen === '$$' || mathOpen === '\\[', options));
          i = end + mathClose.length;
          continue;
        }
      }
      if (text[i] === '`') {
        const marks = rest.match(/^`+/)[0];
        const end = text.indexOf(marks, i + marks.length);
        if (end >= 0) {
          flush();
          let content = text.slice(i + marks.length, end).replace(/\n/g, ' ');
          if (/^ .* $/.test(content) && content.trim()) content = content.slice(1, -1);
          out.append(node('code', content));
          i = end + marks.length;
          continue;
        }
      }
      if (text[i] === '[') {
        const link = linkAt(text, i);
        if (link) {
          const checked = safeLink(link.destination);
          flush();
          if (checked) {
            const element = node('a');
            element.href = checked.value;
            if (link.title) element.title = decodeEntities(link.title);
            if (checked.external) {
              element.target = '_blank';
              element.rel = 'noopener noreferrer';
            } else {
              element.dataset.docLink = checked.value;
              element.dataset.basePath = options.basePath || '';
            }
            element.append(inline(link.label, options, (depth || 0) + 1));
            out.append(element);
          } else {
            out.append(inline(link.label, options, (depth || 0) + 1));
          }
          i = link.end;
          continue;
        }
      }
      const emphasis = rest.startsWith('**') ? '**' : rest.startsWith('__') ? '__' : text[i] === '*' ? '*' : text[i] === '_' ? '_' : null;
      if (emphasis && !(/\w/.test(text[i - 1] || '') && emphasis.includes('_'))) {
        const end = text.indexOf(emphasis, i + emphasis.length);
        if (end > i + emphasis.length && !/\s/.test(text[i + emphasis.length]) && !/\s/.test(text[end - 1])) {
          flush();
          const element = node(emphasis.length === 2 ? 'strong' : 'em');
          element.append(inline(text.slice(i + emphasis.length, end), options, (depth || 0) + 1));
          out.append(element);
          i = end + emphasis.length;
          continue;
        }
      }
      if (text[i] === '\\' && /[\\`*{}\[\]#+.!_|>~$-]/.test(text[i + 1] || '')) {
        buffer += text[i + 1]; i += 2; continue;
      }
      buffer += text[i++];
    }
    flush();
    return out;
  }

  function indentation(line) {
    const prefix = line.match(/^[ \t]*/)[0];
    return prefix.replace(/\t/g, '    ').length;
  }

  function splitCells(line) {
    const clean = line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '');
    const cells = [];
    let cell = '', ticks = 0;
    for (let i = 0; i < clean.length; i++) {
      if (clean[i] === '\\' && clean[i + 1] === '|') { cell += '|'; i++; continue; }
      if (clean[i] === '`') {
        const run = clean.slice(i).match(/^`+/)[0].length;
        ticks = ticks === run ? 0 : ticks || run;
        cell += '`'.repeat(run); i += run - 1; continue;
      }
      if (clean[i] === '|' && !ticks) { cells.push(cell.trim()); cell = ''; }
      else cell += clean[i];
    }
    cells.push(cell.trim());
    return cells;
  }

  function tableDivider(line) {
    if (!line || !line.includes('|')) return false;
    const cells = splitCells(line);
    return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
  }

  function special(line, next) {
    return !line.trim() || fenceStart.test(line) || headingStart.test(line) ||
      /^ {0,3}>/.test(line) || listStart.test(line) ||
      /^ {0,3}(?:\*\s*){3,}$/.test(line) || /^ {0,3}(?:-\s*){3,}$/.test(line) ||
      /^ {0,3}(?:_\s*){3,}$/.test(line) || anchorTag.test(line.trim()) ||
      /^ {0,3}(?:\$\$|\\\[)/.test(line) || (line.includes('|') && tableDivider(next));
  }

  function blocks(lines, options, ids) {
    const out = doc.createDocumentFragment();
    for (let i = 0; i < lines.length;) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      const fence = line.match(fenceStart);
      if (fence) {
        const body = [];
        const closing = new RegExp('^ {0,3}' + (fence[1][0] === '`' ? '`' : '~') + '{' + fence[1].length + ',}\\s*$');
        i++;
        while (i < lines.length && !closing.test(lines[i])) body.push(lines[i++]);
        if (i < lines.length) i++;
        const pre = node('pre'), code = node('code', body.join('\n'));
        const language = fence[2].trim().split(/\s+/)[0].replace(/[^a-z\d_-]/gi, '');
        if (language) code.className = 'language-' + language;
        pre.append(code); out.append(pre); continue;
      }
      const display = line.match(/^ {0,3}(\$\$|\\\[)/);
      if (display) {
        const close = display[1] === '\\[' ? '\\]' : '$$';
        const collected = [];
        let closingLine = -1;
        for (let current = i; current < lines.length; current++) {
          const start = current === i ? display[0].length : 0;
          const end = mathCloseAt(lines[current], close, start);
          if (end >= 0) {
            if (!lines[current].slice(end + close.length).trim()) {
              collected.push(lines[current].slice(start, end));
              closingLine = current;
            }
            break;
          }
          collected.push(lines[current].slice(start));
        }
        if (closingLine >= 0) {
          const source = lines.slice(i, closingLine + 1).join('\n').trim();
          out.append(renderedMath(source, collected.join('\n'), true, options));
          i = closingLine + 1; continue;
        }
      }
      const heading = line.match(headingStart);
      const setext = i + 1 < lines.length && /^ {0,3}(?:=+|-+)\s*$/.test(lines[i + 1]);
      if (heading || (setext && !special(line))) {
        const text = heading ? heading[2].replace(/\s+#+\s*$/, '') : line.trim();
        const level = heading ? heading[1].length : lines[i + 1].trim()[0] === '=' ? 1 : 2;
        const h = node('h' + level);
        h.append(inline(text, options));
        const plainHeading = inline(text, Object.assign({}, options, {renderMath: false}));
        h.dataset.tocLabel = plainHeading.textContent;
        const base = slug(plainHeading.textContent) || 'section';
        const count = ids.get(base) || 0;
        ids.set(base, count + 1);
        h.id = base + (count ? '-' + count : '');
        out.append(h); i += heading ? 1 : 2; continue;
      }
      if (/^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$/.test(line)) {
        out.append(node('hr')); i++; continue;
      }
      if (/^ {0,3}>/.test(line)) {
        const quote = [];
        while (i < lines.length && /^ {0,3}>/.test(lines[i])) quote.push(lines[i++].replace(/^ {0,3}> ?/, ''));
        const blockquote = node('blockquote');
        blockquote.append(blocks(quote, options, ids)); out.append(blockquote); continue;
      }
      if (line.includes('|') && tableDivider(lines[i + 1])) {
        const titles = splitCells(line), alignments = splitCells(lines[i + 1]);
        const table = node('table'), thead = node('thead'), tbody = node('tbody');
        function row(cells, tag) {
          const tr = node('tr');
          titles.forEach(function (_, index) {
            const cell = node(tag);
            cell.append(inline(cells[index] || '', options));
            if (tag === 'th') cell.scope = 'col';
            const alignment = alignments[index] || '';
            if (alignment.startsWith(':') && alignment.endsWith(':')) cell.style.textAlign = 'center';
            else if (alignment.endsWith(':')) cell.style.textAlign = 'right';
            tr.append(cell);
          });
          return tr;
        }
        thead.append(row(titles, 'th')); i += 2;
        while (i < lines.length && lines[i].trim() && lines[i].includes('|')) tbody.append(row(splitCells(lines[i++]), 'td'));
        table.append(thead, tbody);
        const container = node('div'); container.className = 'md-table-scroll'; container.append(table);
        out.append(container); continue;
      }
      const list = line.match(listStart);
      if (list) {
        const ordered = /^\d/.test(list[2]), base = indentation(line);
        const container = node(ordered ? 'ol' : 'ul');
        if (ordered && parseInt(list[2], 10) !== 1) container.start = parseInt(list[2], 10);
        while (i < lines.length) {
          const item = lines[i].match(listStart);
          if (!item || indentation(lines[i]) !== base || /^\d/.test(item[2]) !== ordered) break;
          const contentIndent = base + item[2].length + 1;
          const content = [item[3]];
          i++;
          while (i < lines.length) {
            const next = lines[i], nextItem = next.match(listStart);
            if (nextItem && indentation(next) <= base) break;
            if (!next.trim()) {
              let look = i + 1;
              while (look < lines.length && !lines[look].trim()) look++;
              if (look >= lines.length || indentation(lines[look]) <= base) { i = look; break; }
              content.push(''); i++; continue;
            }
            if (indentation(next) <= base && special(next, lines[i + 1])) break;
            const expanded = next.replace(/^\t+/, tabs => '    '.repeat(tabs.length));
            content.push(indentation(next) > base ? expanded.slice(Math.min(contentIndent, indentation(next))) : next);
            i++;
          }
          const li = node('li'), rendered = blocks(content, options, ids);
          if (rendered.childNodes.length === 1 && rendered.firstChild.nodeName === 'P') {
            while (rendered.firstChild.firstChild) li.append(rendered.firstChild.firstChild);
          } else li.append(rendered);
          container.append(li);
        }
        out.append(container); continue;
      }
      // Empty anchor tags are layout-free navigation targets, never interpreted HTML.
      if (anchorTag.test(line.trim())) {
        out.append(inline(line.trim(), options)); i++; continue;
      }
      const paragraph = [line];
      i++;
      while (i < lines.length && !special(lines[i], lines[i + 1])) {
        if (i + 1 < lines.length && /^ {0,3}(?:=+|-+)\s*$/.test(lines[i + 1])) break;
        paragraph.push(lines[i++]);
      }
      const p = node('p'); p.append(inline(paragraph.join('\n'), options)); out.append(p);
    }
    return out;
  }

  function render(text, options) {
    return blocks(String(text == null ? '' : text).replace(/\r\n?/g, '\n').split('\n'), options || {}, new Map());
  }

  window.TauMarkdown = Object.freeze({render, slug});
})();
