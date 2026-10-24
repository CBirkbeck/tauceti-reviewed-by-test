// The sign-in helper, with GitHub's token endpoint stubbed: node --test signin/
import {test, beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import worker from './worker.js';

const SITE = 'https://cbirkbeck.github.io';
const ENV = {CLIENT_ID: 'Iv23test', CLIENT_SECRET: 's3cret', ALLOWED_ORIGINS: `${SITE}, http://127.0.0.1:8000`};
const VERIFIER = 'v'.repeat(43), CALLBACK = 'https://cbirkbeck.github.io/tauceti-reviewed-by-test/';
const GOOD = {code: 'abc123', code_verifier: VERIFIER, redirect_uri: CALLBACK};

let sent;
// GitHub's token endpoint answering `reply`; what it was sent is kept in `sent`.
function github(reply, status = 200) {
  globalThis.fetch = async (url, init) => {
    sent.push({url, headers: init.headers, body: JSON.parse(init.body)});
    return new Response(JSON.stringify(reply), {status, headers: {'Content-Type': 'application/json'}});
  };
}
beforeEach(() => {
  sent = [];
  github({access_token: 'ghu_token', token_type: 'bearer', expires_in: 28800, refresh_token: 'ghr_refresh',
          refresh_token_expires_in: 15897600, scope: ''});
});
const ask = (body, {origin = SITE, method = 'POST', path = '/token', env = ENV} = {}) =>
  worker.fetch(new Request('https://tauceti-review-signin.example.workers.dev' + path, {method, headers: {Origin: origin,
    'Content-Type': 'application/json'}, body: method === 'POST' ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined}), env);

test('swaps a code for a token, with the secret, for the site', async () => {
  const r = await ask(GOOD);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('Access-Control-Allow-Origin'), SITE);
  assert.equal(r.headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(await r.json(), {access_token: 'ghu_token', token_type: 'bearer', expires_in: 28800}, 'and not the refresh token');
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, 'https://github.com/login/oauth/access_token');
  assert.equal(sent[0].headers.Accept, 'application/json');
  assert.deepEqual(sent[0].body, {client_id: 'Iv23test', client_secret: 's3cret', code: 'abc123', code_verifier: VERIFIER,
                                  redirect_uri: CALLBACK});
});

test('answers the preflight of an allowed site, and of no other', async () => {
  const r = await ask(null, {method: 'OPTIONS'});
  assert.equal(r.status, 204);
  assert.equal(r.headers.get('Access-Control-Allow-Origin'), SITE);
  assert.equal(r.headers.get('Access-Control-Allow-Methods'), 'POST');
  assert.equal(r.headers.get('Access-Control-Allow-Headers'), 'Content-Type');
  const local = await ask(null, {method: 'OPTIONS', origin: 'http://127.0.0.1:8000'});
  assert.equal(local.headers.get('Access-Control-Allow-Origin'), 'http://127.0.0.1:8000', 'each origin the settings list');
  const other = await ask(null, {method: 'OPTIONS', origin: 'https://evil.example'});
  assert.equal(other.status, 403);
  assert.equal(other.headers.get('Access-Control-Allow-Origin'), null);
});

test('refuses other sites, without asking GitHub', async () => {
  for (const origin of ['https://evil.example', 'https://cbirkbeck.github.io.evil.example', '']) {
    const r = await ask(GOOD, {origin});
    assert.equal(r.status, 403, origin);
    assert.equal(r.headers.get('Access-Control-Allow-Origin'), null, origin);
  }
  assert.equal(sent.length, 0);
});

test('refuses what is not a code, without asking GitHub', async () => {
  const bad = [{}, {code: ''}, {code: 'a b'}, {code: 7}, {...GOOD, code_verifier: 'short'}, {...GOOD, code_verifier: 'x'.repeat(129)},
               {...GOOD, redirect_uri: 'javascript:alert(1)'}, {...GOOD, redirect_uri: 5}];
  for (const body of [...bad, 'not json']) {
    const r = await ask(body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal((await r.json()).error, 'bad_request');
  }
  assert.equal(sent.length, 0);
  const plain = await ask({code: 'abc123'});
  assert.equal(plain.status, 200, 'a code alone is enough: GitHub decides');
  assert.deepEqual(sent[0].body, {client_id: 'Iv23test', client_secret: 's3cret', code: 'abc123'});
});

test("passes on GitHub's refusal", async () => {
  github({error: 'bad_verification_code', error_description: 'The code passed is incorrect or expired.'});
  const r = await ask(GOOD);
  assert.equal(r.status, 400);
  assert.equal(r.headers.get('Access-Control-Allow-Origin'), SITE, 'which the page can read');
  assert.deepEqual(await r.json(), {error: 'bad_verification_code', error_description: 'The code passed is incorrect or expired.'});
  github({message: 'Server Error'}, 500);
  assert.deepEqual(await (await ask(GOOD)).json(), {error: 'github_error', error_description: 'GitHub answered 500'});
  globalThis.fetch = async () => { throw new TypeError('fetch failed'); };
  const down = await ask(GOOD);
  assert.equal(down.status, 502);
  assert.equal((await down.json()).error, 'github_unreachable');
});

test('says so when it has no secret yet', async () => {
  const r = await ask(GOOD, {env: {...ENV, CLIENT_SECRET: undefined}});
  assert.equal(r.status, 500);
  assert.equal((await r.json()).error, 'not_configured');
  assert.equal(sent.length, 0);
});

test('only POST /token', async () => {
  assert.equal((await ask(null, {method: 'GET'})).status, 405);
  assert.equal((await ask(GOOD, {path: '/'})).status, 404);
  assert.equal((await ask(GOOD, {path: '/token/x'})).status, 404);
});
