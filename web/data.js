/* Tau Ceti Review: the data the build wrote (scripts/site_data.py), fetched as pages need it and
   kept. Nothing is computed here that the build could have: this only finds and unpacks. */
(function () {
  'use strict';
  const cache = new Map();
  function json(path) {
    if (!cache.has(path)) {
      cache.set(path, fetch('data/' + path).then(r => {
        if (!r.ok) throw new Error(`data/${path}: ${r.status}`);
        return r.json();
      }).catch(e => { cache.delete(path); throw e; }));
    }
    return cache.get(path);
  }
  const KINDS = {t: 'theorem', d: 'definition', s: 'structure', c: 'class', n: 'inductive', i: 'instance', a: 'axiom', o: 'opaque'};
  const FLAG = Object.freeze({PROJECT: 1, NAMED: 2, BASIC: 4, ROUTINE: 8, DOCUMENTED: 16, AUX: 32, SORRY: 64});
  const STATES = ['unreviewed', 'covered', 'uncounted', 'stale', 'problem', 'disputed'];
  let META = null;

  /* FNV-1a over UTF-16 code units: the shard of a name in data/names/ (scripts/common.py, fnv_shard). */
  function fnv(name, shards) {
    let h = 0x811C9DC5;
    for (let i = 0; i < name.length; i++) { h ^= name.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h % shards;
  }
  async function meta() { if (!META) META = await json('meta.json'); return META; }
  function unpack(id, r) {
    return {id, name: r[0], kind: KINDS[r[1]] || 'definition', flags: r[2], mod: r[3], title: r[4],
            state: [STATES[r[5]] || 'unreviewed', STATES[r[6]] || 'unreviewed'], m: r[7], p: r[8], nm: r[9], np: r[10],
            brief: r[11] || '', ml: r[12] || 0, nd: r[13] || 0};
  }
  async function node(id) {
    const m = await meta();
    const rows = await json(`nodes/${Math.floor(id / m.shards.nodes)}.json`);
    const r = rows[id % m.shards.nodes];
    return r ? unpack(id, r) : null;
  }
  const nodes = async ids => (await Promise.all([...new Set(ids)].map(node))).filter(Boolean);
  async function idOf(name) {
    const m = await meta();
    const rows = await json(`names/${fnv(name, m.shards.names)}.json`);
    const hit = rows.find(r => r[1] === name);
    return hit ? hit[0] : null;
  }
  /* A declaration: its node, and for one of the library's its entry and module (data/m/<n>.json). */
  async function decl(name) {
    const id = await idOf(name);
    if (id == null) return null;
    const n = await node(id);
    if (!(n.flags & FLAG.PROJECT) || n.mod < 0) return {node: n, entry: null, module: null};
    const module = await json(`m/${n.mod}.json`);
    return {node: n, entry: module.decls.find(e => e.id === id) || null, module};
  }
  async function moduleByName(name) {
    const rows = await json('modules.json');
    const n = rows.findIndex(r => r[0] === name);
    return n < 0 ? null : {index: n, row: rows[n], file: n < (await meta()).counts.modules ? await json(`m/${n}.json`) : null};
  }
  window.TauData = Object.freeze({
    json, meta, node, nodes, idOf, decl, moduleByName, fnv, KINDS, FLAG, STATES,
    modules: () => json('modules.json'), named: () => json('named.json'), search: () => json('search.json'),
    titles: () => json('titles.json'), activity: () => json('activity.json'), upstream: () => json('upstream.json'),
  });
})();
