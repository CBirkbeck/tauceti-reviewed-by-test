/* Tau Ceti Review: signing in with GitHub, so that an answer is filed from the page, under the reader's own
   account, with no trip to GitHub's form. The site's GitHub App (settings.json's `signin`) has one permission,
   issues, and is installed on the review repository alone. GitHub hands the page a one-time code; the sign-in
   helper (signin/worker.js) swaps it for a token with the app's secret, which no page can hold; the token then
   lives in this browser only, for the eight hours GitHub gives it. Without `signin`, or signed out, the forms
   open on GitHub filled in, as before. */
(function () {
  'use strict';
  const KEY = 'tauceti-review:github', PENDING = 'tauceti-review:signin';
  const API = 'https://api.github.com';

  /* What the page keeps: the sign-in in localStorage, a sign-in under way in this tab's sessionStorage. A browser
     that keeps nothing still works: signed out. */
  const area = tab => tab ? window.sessionStorage : window.localStorage;
  function load(key, tab) { try { return JSON.parse(area(tab).getItem(key) || 'null'); } catch (e) { return null; } }
  function keep(key, value, tab) { try { area(tab).setItem(key, JSON.stringify(value)); return true; } catch (e) { return false; } }
  function forget(key, tab) { try { area(tab).removeItem(key); } catch (e) { /* nothing kept */ } }

  const configured = meta => !!(meta.signin && meta.signin.client_id && meta.signin.exchange);
  const callback = meta => meta.signin.callback || meta.site.url;
  /* The reader's sign-in while its token lasts, with a minute to spare: {token, login, expires}. */
  function session() {
    const s = load(KEY);
    return s && s.token && s.login && s.expires > Date.now() + 60000 ? s : null;
  }
  function signOut() { forget(KEY); }

  class GitHubError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }
  async function github(token, method, path, body) {
    let r;
    try {
      r = await fetch(API + path, {method, body: body ? JSON.stringify(body) : undefined,
        headers: {Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                  ...(body ? {'Content-Type': 'application/json'} : {})}});
    } catch (e) {
      throw new GitHubError(0, 'GitHub could not be reached');
    }
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) forget(KEY);  // the token has ended, or was revoked: signed out
    if (!r.ok) throw new GitHubError(r.status, data.message || `GitHub answered ${r.status}`);
    return data;
  }

  /* PKCE (RFC 7636): the code GitHub hands back is worth nothing without the verifier this tab keeps. */
  const b64url = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const random = n => b64url(crypto.getRandomValues(new Uint8Array(n)));
  const challenge = async verifier => b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));

  /* Off to GitHub to sign in, and back to this page as it is. `then` is what to do on return, such as an answer
     to file; this tab keeps it meanwhile. */
  async function signIn(meta, then) {
    const state = random(16), verifier = random(32);
    if (!keep(PENDING, {state, verifier, hash: location.hash, then: then || null}, true)) {
      throw new GitHubError(0, 'this browser keeps nothing for the page, which signing in needs');
    }
    const q = new URLSearchParams({client_id: meta.signin.client_id, redirect_uri: callback(meta), state,
                                   code_challenge: await challenge(verifier), code_challenge_method: 'S256'});
    location.assign('https://github.com/login/oauth/authorize?' + q);
  }

  /* Back from GitHub, with `?code=…&state=…` or `?error=…`: checks the state, has the helper swap the code for a
     token, asks GitHub whose it is, keeps both, and puts the address back as it was. Returns what was to be done
     on return, `then`, with `login` or with why signing in failed, `error`; null when this is no return from
     GitHub. */
  async function finish(meta) {
    const q = new URLSearchParams(location.search);
    if (!q.has('state') || !(q.has('code') || q.has('error'))) return null;
    const pending = load(PENDING, true);
    forget(PENDING, true);
    history.replaceState(null, '', location.pathname + ((pending && pending.hash) || location.hash));
    const then = pending ? pending.then : null;
    if (!pending || pending.state !== q.get('state')) return {then, error: 'Not signed in: the reply from GitHub could not be checked. Try again.'};
    if (q.has('error')) {
      return {then, error: q.get('error') === 'access_denied' ? 'Not signed in: GitHub was not given access.'
                                                              : `Not signed in: ${q.get('error_description') || q.get('error')}.`};
    }
    try {
      let r;
      try {
        r = await fetch(meta.signin.exchange, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({code: q.get('code'), code_verifier: pending.verifier, redirect_uri: callback(meta)})});
      } catch (e) {
        return {then, error: 'Not signed in: the sign-in helper could not be reached.'};
      }
      const t = await r.json().catch(() => ({}));
      if (!r.ok || !t.access_token) return {then, error: `Not signed in: ${t.error_description || t.error || 'the sign-in helper answered ' + r.status}.`};
      const user = await github(t.access_token, 'GET', '/user');
      keep(KEY, {token: t.access_token, login: user.login, expires: Date.now() + (t.expires_in || 28800) * 1000});
      return {then, login: user.login};
    } catch (e) {
      return {then, error: `Not signed in: ${e.message}.`};
    }
  }

  /* As the signed-in reader: an issue on the review repository, {number, url}; a comment on one. */
  async function file(meta, issue) {
    const s = session();
    if (!s) throw new GitHubError(401, 'not signed in');
    const r = await github(s.token, 'POST', `/repos/${meta.store.repo}/issues`, issue);
    return {number: r.number, url: r.html_url};
  }
  async function comment(meta, number, body) {
    const s = session();
    if (!s) throw new GitHubError(401, 'not signed in');
    await github(s.token, 'POST', `/repos/${meta.store.repo}/issues/${number}/comments`, {body});
  }

  window.TauSignin = Object.freeze({configured, session, signIn, finish, signOut, file, comment});
})();
