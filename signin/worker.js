/* Tau Ceti Review's sign-in helper, on Cloudflare Workers: the one step of signing in with GitHub that a page
   cannot take itself. GitHub hands the page a one-time code; swapping it for a token takes the GitHub App's client
   secret, which no page can hold, and GitHub's token endpoint does not answer browsers. The page posts the code
   here (POST /token {code, code_verifier, redirect_uri}); this posts it on to GitHub with the secret, and returns
   the token, which then lives in the reader's browser alone. Nothing is kept here.

   Its settings (wrangler.toml): CLIENT_ID, the app's client ID; ALLOWED_ORIGINS, the sites whose pages may ask,
   comma-separated; and the secret CLIENT_SECRET, which `wrangler secret put CLIENT_SECRET` takes. */
const GITHUB = 'https://github.com/login/oauth/access_token';

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowed = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean).includes(origin);
    const cors = allowed ? {'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Methods': 'POST',
                            'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '86400'} : {};
    const reply = (status, body) => new Response(body === null ? null : JSON.stringify(body), {status,
      headers: {...cors, Vary: 'Origin', 'Cache-Control': 'no-store', ...(body === null ? {} : {'Content-Type': 'application/json'})}});
    if (new URL(request.url).pathname !== '/token') return reply(404, {error: 'not_found'});
    if (!allowed) return reply(403, {error: 'origin_not_allowed'});
    if (request.method === 'OPTIONS') return reply(204, null);
    if (request.method !== 'POST') return reply(405, {error: 'method_not_allowed'});
    const input = await request.json().catch(() => null);
    const {code, code_verifier: verifier, redirect_uri: redirect} = input || {};
    if (typeof code !== 'string' || !/^[\w-]{1,256}$/.test(code)
        || (verifier != null && (typeof verifier !== 'string' || !/^[\w.~-]{43,128}$/.test(verifier)))
        || (redirect != null && (typeof redirect !== 'string' || !/^https?:\/\/\S+$/.test(redirect)))) {
      return reply(400, {error: 'bad_request', error_description: 'a code, with its verifier and redirect address'});
    }
    if (!env.CLIENT_ID || !env.CLIENT_SECRET) return reply(500, {error: 'not_configured', error_description: 'the helper has no client ID or secret yet'});
    const params = {client_id: env.CLIENT_ID, client_secret: env.CLIENT_SECRET, code,
                    ...(verifier ? {code_verifier: verifier} : {}), ...(redirect ? {redirect_uri: redirect} : {})};
    let r;
    try {
      r = await fetch(GITHUB, {method: 'POST', body: JSON.stringify(params),
        headers: {Accept: 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'tauceti-review-signin'}});
    } catch (e) {
      return reply(502, {error: 'github_unreachable', error_description: 'GitHub could not be reached'});
    }
    const t = await r.json().catch(() => ({}));
    if (!r.ok || t.error || !t.access_token) {
      return reply(400, {error: t.error || 'github_error', error_description: t.error_description || `GitHub answered ${r.status}`});
    }
    // Not the refresh token: the page signs in again when this one ends.
    return reply(200, {access_token: t.access_token, token_type: t.token_type || 'bearer', expires_in: t.expires_in || null});
  },
};
