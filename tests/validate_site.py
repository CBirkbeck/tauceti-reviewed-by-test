#!/usr/bin/env python3
"""The browser check: serves a built site as GitHub Pages would and checks, in Chromium, what a
reader does: the shell and its two themes, the old addresses, the home page, the Named page, search,
a declaration, its review box and its one question, the Reviewed page, formulas typeset, its dependency
map, the other pages, and a phone. Without --site it
builds the fixture's site first (tests/fixture_site.py).

  python3 tests/validate_site.py [--site DIR | --url URL] [--only NAME,NAME] [--smoke]

`--smoke` checks a real build instead of the fixture's (`--site _site`, or the published site with
`--url`): the pages open without errors, and the first named declarations draw their maps.
Prints one line per check, then PASS (exit 0) or FAIL (exit 1). Errors in the page's console fail
the check that met them.
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import http.server
import json
import re
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CHECKS = {}


class Fail(AssertionError):
    pass


def check(fn):
    CHECKS[fn.__name__] = fn
    return fn


def expect(condition, what: str) -> None:
    if not condition:
        raise Fail(what)


def visit(browser, url: str, route: str, errors: list, before=None, **context):
    page = browser.new_context(**({"viewport": {"width": 1440, "height": 900}} | context)).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    if before:
        before(page)
    page.goto(url + route, wait_until="load")
    page.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
    return page


def settle(page, route: str) -> None:
    page.wait_for_function(f"TauReview.route() === {route!r} && TauReview.ready", timeout=30000)


@check
def shell(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    expect(page.locator(".brand").inner_text().strip() == "Tau Ceti Review", "the top bar names the site")
    expect(page.locator(".nav a").all_inner_texts() == ["Named", "Reviewed", "Browse", "Activity", "How to review"], "and its sections")
    expect("Fixture at B" in page.locator("#foot").inner_text(), "the footer names the pinned commit")
    background = "getComputedStyle(document.body).backgroundColor"
    expect(page.evaluate(background) == "rgb(11, 16, 22)", "dark at first, in the Atlas's colours")
    page.click("#theme")
    expect(page.evaluate(background) == "rgb(251, 250, 247)", "light at a click")
    page.reload(wait_until="load")
    page.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
    expect(page.evaluate(background) == "rgb(251, 250, 247)", "and light it stays")
    expect(page.evaluate("[TauReview.fnv('TauCeti.Place', 64), TauReview.fnv('Fixture.«term𝟚_»', 64), TauReview.fnv('ℝ', 64)]")
           == [47, 38, 8], "the page shards names as scripts/common.py does")


@check
def old_addresses(browser, url, errors):
    page = visit(browser, url, "#d=Fixture.double", errors)
    expect(page.evaluate("location.hash") == "#/d/Fixture.double", "#d= opens the declaration")
    page = visit(browser, url, "#q=triple", errors)
    expect(page.evaluate("location.hash") == "#/search/triple", "#q= searches")


@check
def home(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    expect(page.locator("h1").inner_text() == "Review the mathematics in Fixture", "the home page")
    expect(page.locator(".stat").count() == 6 and page.locator("a.card").count() == 5, "its counts and its tiles")
    expect(page.locator("a.stat[href='#/reviewed'] b").inner_text() == "11", "how many are reviewed, a click from the list of them")
    expect(page.locator(".section", has_text="Latest named").locator(".list > li").count() == 2, "the latest named")
    expect(page.locator(".section", has_text="Areas").locator("a.chip").count() == 3, "the areas")
    still = page.locator("a.stat[href='#/activity/open']")
    expect(still.locator("span").inner_text() == "no, still open", "the noes still open, counted")
    n = still.locator("b").inner_text()
    still.click()
    page.wait_for_function("location.hash === '#/activity/open' && window.TauReview.ready")
    open_ = page.locator("section#open")
    expect(open_.locator("h2").inner_text().startswith("Answered no, still open")
           and str(open_.locator(".records > .thread").count()) == n and open_.locator("a.decl-link").count() == int(n),
           "and a click from which they are")
    # Scrolled to them: at the top, below the bar that stays there.
    expect(page.evaluate("(() => { const top = document.getElementById('open').getBoundingClientRect().top;"
                         " return top >= 0 && top < 150; })()"), "scrolled to them")


@check
def named(browser, url, errors):
    page = visit(browser, url, "#/named", errors)
    expect(page.locator(".list > li").count() == 2, "both announcements are listed")
    expect([h.split("\n")[0] for h in page.locator("main h2").all_inner_texts()] == ["Basic", "Uses"], "grouped by area")
    page.check("#ai")
    page.wait_for_function("TauReview.ready && document.querySelector('#ai') && document.querySelector('#ai').checked")
    expect(page.evaluate("localStorage.getItem('tauceti-review:ai')") == "1", "counting AI reviews is kept")
    page.click("[data-what=definition]")
    expect(page.locator(".list > li").count() == 1 and "Being double" in page.locator(".list > li").inner_text(), "the definitions filter")
    page.click(".list > li a")
    settle(page, "decl:Fixture.IsDouble")
    expect(page.locator("h1").inner_text() == "Being double", "an item opens its declaration, titled by Voyager")
    expect("is twice" not in page.locator("main").inner_text() and page.locator(".links a", has_text="Voyager's post").count() == 1,
           "Voyager's sentence is not repeated on the page, its post a link away")


@check
def search(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    page.fill("#q", "triple")
    settle(page, "search:triple")
    expect(page.locator(".list .item-sub").first.inner_text().startswith("Fixture.triple"), "a name finds its declarations")
    page.fill("#q", "leaves alone")
    settle(page, "search:leaves alone")
    expect("Fixture.triple" in page.locator(".list .item-sub").all_inner_texts(), "words from a title find it")


@check
def declaration(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    expect(page.locator("h1").inner_text() == "A definition that version B leaves alone.", "titled by its docstring")
    expect(page.locator(".kind-row .kind").inner_text().lower() == "definition", "its kind")
    expect(page.locator(".lean pre").first.inner_text() == "def Fixture.triple (n : Nat) : Nat", "its signature, as the docs show it")
    expect(page.locator(".lean details:not([open]) summary", has_text="Definition").count() == 1, "its value, folded as in the docs")
    expect(page.locator("main > .md.prose").count() == 0, "a docstring that is all title is not said twice")
    expect(page.evaluate("[TauReview.afterTitle('First, wrapped\\nhere. Then more.', 'First, wrapped here.'), "
                         "TauReview.afterTitle('# A heading\\nText.', 'Text.'), TauReview.afterTitle('Only this.', 'Only this.')]")
           == ["Then more.", "# A heading\nText.", ""], "below a title, the docstring goes on from its second sentence")
    leads = page.evaluate("""[
      ["**Strassmann's theorem.** Let f be.", "Strassmann's theorem"],
      ["**Molien's formula**: the image.", "Molien's formula"],
      ["**Invariance of domain.** Let M.", "Brouwer's invariance of domain"],
      ["**Max-flow/min-cut theorem.** For c.", "The max-flow min-cut theorem"],
      ["**The Lindemann–Weierstrass theorem**, in Baker's form.", "The Lindemann–Weierstrass theorem"],
      ["**The cyclic Hasse norm theorem, placewise.** For L.", "The Hasse norm theorem"],
      ["**Construction B** of a code.", "Construction B"],
    ].map(([doc, title]) => TauReview.afterLead(doc, title))""")
    expect(leads == ["Let f be.", "The image.", "Let M.", "For c.", "**The Lindemann–Weierstrass theorem**, in Baker's form.",
                     "**The cyclic Hasse norm theorem, placewise.** For L.", "**Construction B** of a code."],
           "under Voyager's title, a bold opening that only names it goes, and one that says more stays")
    hrefs = page.eval_on_selector_all(".links a", "as => as.map(a => a.href)")
    expect("https://example.org/docs/Fixture/Basic.html#Fixture.triple" in hrefs, "the API docs")
    expect("https://github.com/test/fixture/blob/B/Fixture/Basic.lean#L15-L16" in hrefs, "the source at the pin")
    expect(page.locator("h2", has_text="Results about it").count() == 0 and page.locator("h2", has_text="What it is built from").count() == 0,
           "what it is built from and the results about it are the map's, not lists")
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    expect(page.locator(".lean pre").first.inner_text() == "theorem Fixture.triple_pos (n : Nat) (h : 0 < n) : 0 < Fixture.triple n",
           "a theorem's signature, section variables and all")
    ref = page.locator(".lean a.ref", has_text="Fixture.triple")
    expect(ref.get_attribute("href") == "#/d/Fixture.triple", "its names link")
    expect(page.locator(".lean details").count() == 0 and "omega" not in page.inner_text("main"), "no proof")
    expect(page.locator("h2", has_text="What it is about").count() == 0, "what a theorem is about is the map's, not a list")
    ref.hover()
    page.wait_for_selector(".tip")
    card = page.locator(".tip").first
    expect("Fixture.triple · Definition" in card.inner_text() and "def Fixture.triple (n : Nat) : Nat" in card.locator(".lean pre").first.inner_text(),
           "a name's card on hover: what it is, and its signature")
    inner = card.locator("a.ref[data-name]").first
    inner_name = inner.get_attribute("data-name")
    inner.hover()
    page.wait_for_function("document.querySelectorAll('.tip').length === 2")
    expect(inner_name in page.locator(".tip").nth(1).inner_text(), "a name in the card opens its own card on top")
    page.mouse.move(2, 2)
    page.wait_for_function("document.querySelectorAll('.tip').length === 0")
    page.locator(".lean .var[data-var=n]").first.hover()
    page.wait_for_selector(".tip")
    expect("n : Nat" in page.locator(".tip").first.inner_text() and page.locator("main .lean .var.hit").count() == 3,
           "a variable's card is its type, and its uses light up")


def on_github(url: str, kind: str):
    """What a "Send on GitHub" address files, as GitHub, the Label answers workflow and intake read it: its
    title, the label scripts/label_issue.py gives it, and its answers as evidence-store parses them. A title and
    a body only: no form (`template`), which GitHub has opened as an empty issue, dropping what was written
    (#79, #80), and no `labels`, which GitHub refuses to anyone who may not label."""
    sys.path.insert(0, str(HERE.parent / "scripts"))
    from evidence_store import forms
    from label_issue import TEMPLATES, label_for, template_forms
    u, q = urlparse(url), parse_qs(urlparse(url).query)
    expect(f"{u.scheme}://{u.netloc}{u.path}" == "https://github.com/example/fixture-store/issues/new"
           and sorted(q) == ["body", "title"], f"a new issue on GitHub, its title and body only: {url}")
    title, body = q["title"][0], q["body"][0]
    return title, label_for({"title": title, "body": body}, template_forms(TEMPLATES)), forms.parse(kind, body)


def without_signin(page):
    """The site as it is with no sign-in in its settings: data/meta.json without `signin`."""
    def handle(route):
        r = route.fetch()
        meta = r.json()
        meta.pop("signin", None)
        route.fulfill(response=r, json=meta)
    page.route("**/data/meta.json", handle)


@check
def review(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors, before=without_signin)
    box = page.locator(".review")
    expect(box.locator(".ask").inner_text() == "Is this definition correctly stated?", "one question, naming what it asks about")
    expect(box.locator(".actions button").all_inner_texts() == ["Yes", "No"], "and two answers")
    page.evaluate("window.__opened = []; window.open = u => { window.__opened.push(u); return null; }")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    opened = lambda: page.evaluate("window.__opened[window.__opened.length - 1]")
    shown = box.locator("form.unfold:visible")
    box.locator(".actions button", has_text="Yes").click()
    expect(shown.count() == 1 and shown.locator("button.send").is_enabled(), "yes unfolds its form in the box, a reason optional")
    shown.locator("textarea").fill("Checked against Stacks.")
    shown.locator("button.send").click()
    expect(on_github(opened(), "review") == ("Correctly stated: Fixture.triple", "evidence:review",
                                             {"decl": "Fixture.triple", "commit": "B", "rationale": "Checked against Stacks."})
           and shown.count() == 0 and box.locator(".sent-note:visible").count() == 1,
           "Send opens a new issue on GitHub with the answer written in it as the review form writes it, and says so")
    page.wait_for_function("document.querySelector('.review .sent-note:not([hidden])').textContent.includes('clipboard')")
    expect("### Why\n\nChecked against Stacks." in page.evaluate("navigator.clipboard.readText()"),
           "and what was written is on the clipboard too, should GitHub lose it")
    box.locator(".actions button", has_text="No").click()
    expect(shown.locator("button.send").is_disabled(), "no unfolds the form that asks why, and will not send without it")
    shown.locator("textarea").fill("It is the wrong object.")
    shown.locator("button.send").click()
    expect(on_github(opened(), "problem") == ("Not correctly stated: Fixture.triple", "evidence:problem",
                                              {"decl": "Fixture.triple", "commit": "B", "rationale": "It is the wrong object."}),
           "and opens a new issue on GitHub with the no and its why written in it")
    expect(box.locator(".actions a", has_text="Read it in the API docs").get_attribute("href")
           == "https://example.org/docs/Fixture/Basic.html#Fixture.triple", "the review box links to the docs")
    tally = box.locator(".mark.tally.yes")
    expect(tally.locator(".trailer").inner_text() == "Correctly stated" and tally.locator(".who").inner_text() == "1 person · 1 AI",
           "the yeses, people counted apart from AI agents")
    expect(box.locator(".answers-list .mark.person").count() == 1 and box.locator(".answers-list .mark.agent .ai").count() == 1,
           "each answer's mark, the AI agent's marked")
    colours = page.evaluate("""() => { const probe = document.createElement('span'); document.body.append(probe);
      const of = v => { probe.style.color = `var(${v})`; return getComputedStyle(probe).color; };
      const person = of('--result'), ai = of('--ai'); probe.remove();
      const q = s => getComputedStyle(document.querySelector(s));
      return [q('.answers-list .mark.person .tick').backgroundColor === person, q('.answers-list .mark.agent .tick').color === ai,
              q('.answers-list .mark.agent .ai').color === ai, person !== ai]; }""")
    expect(all(colours), f"a person's yes is a green tick, an AI agent's a blue one, its AI mark blue too ({colours})")
    why = box.locator(".answers-list details.why", has=page.locator(".mark.agent"))
    expect(why.count() == 1 and not why.evaluate("d => d.open"), "the AI agent's reasons, a closed twisty")
    expect(box.locator(".answers-list .mark.stale").count() == 0 and "withdrawn" not in box.locator(".answers-list").inner_text()
           and "earlier version" not in tally.inner_text(), "its answer withdrawn under an old name, left out")
    why.locator("summary").click()
    expect(why.evaluate("d => d.open") and "Compared with its definition" in why.inner_text()
           and why.locator(".twisty-body a[href='https://github.com/example/fixture-store/issues/11']").count() == 1,
           "which opens to why, and its issue")
    expect(box.locator(".mark.tally.tested").count() == 1 and box.locator(".tests-list .pass").count() == 1, "Tested by: the listed test passes")
    test = box.locator(".tests-list details.test").first
    expect("triple_two" in test.locator("summary").inner_text() and "its value at 2" in test.locator("summary").inner_text(),
           "a test, a twisty saying which and what it checks")
    test.locator("summary").click()
    page.wait_for_function("document.querySelector('.tests-list details.test .lean pre')")
    expect("= 6" in test.locator(".lean pre").inner_text(), "which opens to its statement, as the docs show it")
    box.locator(".offer button", has_text="Suggest an improvement").click()
    shown.locator("textarea").fill("State it for any semiring.")
    shown.locator("button.send").click()
    expect(on_github(opened(), "question") == ("What could be better: Fixture.triple", "evidence:question",
                                               {"decl": "Fixture.triple", "commit": "B", "question": "State it for any semiring."}),
           "What could be better: a suggestion unfolds its form, and Send opens it on GitHub with the suggestion in it")
    box.locator(".offer button", has_text="Suggest a test").click()
    expect(shown.locator("textarea").count() == 3, "a test asks what it should satisfy, its Lean statement and what it would catch")
    shown.locator("textarea").first.fill("its value at 0")
    shown.locator("textarea").nth(1).fill("triple 0 = 0 ∧ ∀ n, triple (n + 1) = triple n + 3")
    shown.locator("button.send").click()
    expect(on_github(opened(), "challenge") == ("Suggested test: Fixture.triple", "evidence:challenge",
                                                {"decl": "Fixture.triple", "commit": "B", "property": "its value at 0",
                                                 "statement": "triple 0 = 0 ∧ ∀ n, triple (n + 1) = triple n + 3"}),
           "Tests: a test to suggest unfolds its form, and Send opens it on GitHub with the test in it, symbols and all")
    suggestion = box.locator(".report.question").inner_text()
    expect("suggested by @someone" in suggestion and "any semiring" in suggestion and "Issue #15" in suggestion,
           "and each suggestion shows, with who made it and its issue")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    box.locator(".ai-offer button").click()
    page.wait_for_function("document.querySelector('.ai-offer button').textContent.startsWith('Copied')")
    expected = ("Review Fixture.triple for the Fixture review site, following\n"
                "https://github.com/example/fixture-store/blob/main/AI-REVIEWS.md\n"
                "Give your exact model, as AI-REVIEWS.md says: GPT-6 Astra, not GPT-6.\n"
                "The site shows it at Fixture commit B: https://example.org/#/d/Fixture.triple")
    expect(box.locator(".ai-prompt").is_visible() and box.locator(".ai-prompt").inner_text() == expected,
           "instructions for an AI agent to review it, filled in and shown")
    expect(page.evaluate("navigator.clipboard.readText()") == expected, "and copied with one click")
    expect(page.evaluate("[TauRender.questionWord('theorem', 'lemma'), TauRender.questionWord('structure', 'structure')]")
           == ["lemma", "structure"], "a lemma is asked about as a lemma")
    page = visit(browser, url, "#/d/Fixture.triple_comm", errors)
    box = page.locator(".review")
    expect(box.locator(".ask").inner_text() == "Is this theorem correctly stated?", "a theorem, as a theorem")
    no = box.locator(".mark.tally.no")
    expect(no.locator(".trailer").inner_text() == "Not correctly stated" and no.locator(".who").inner_text() == "1 person",
           "a no still open, counted apart from the yes")
    expect(box.locator(".answers-list .mark.no.person").count() == 1 and box.locator(".answers-list .mark.yes").count() == 1,
           "a cross for the no and a tick for the yes")
    report = box.locator(".report").inner_text()
    expect("answered no by @someone" in report and "the definition, unfolded" in report and "Issue #14" in report,
           "the no in full: who, why, and its issue")
    expect(box.locator(".sub", has_text="Tests").count() == 1 and "No tests yet." in box.inner_text()
           and box.locator(".offer button", has_text="Suggest a test").count() == 1, "Tests, with a test to suggest, where nothing tests it yet")
    expect("No suggestions yet." in box.inner_text(), "What could be better, with nothing suggested yet")
    page = visit(browser, url, "#/d/Fixture.double_zero", errors)
    expect("what it rests on has changed" in page.locator(".review .answers-list").inner_text(), "stale underneath, said")
    page = visit(browser, url, "#/d/Fixture.double", errors)
    box = page.locator(".review")
    expect(box.locator(".answers-list .mark.stale").count() == 1 and "1 on an earlier version" in box.inner_text(),
           "a yes about an earlier version, greyed")
    suggested = box.locator(".tests-list details.test.suggested")
    expect(suggested.count() == 1 and "double n = n + n" in suggested.locator("summary").inner_text(), "the open suggested test")
    suggested.locator("summary").click()
    expect("Suggested by @example" in suggested.inner_text(), "which opens to who suggested it")
    page = visit(browser, url, "#/d/Int", errors)
    # Outside the library too, the statement asked about (asked for on 2026-10-26: `zero_smul` showed none):
    # Lean's printing at the version the library pins, where Mathlib's docs do not say the same.
    expect(page.locator(".lean pre").first.inner_text() == "inductive Int : Type", "outside the library, its statement")
    expect("As Lean prints it at the version Fixture uses" in page.locator(".lean-note").inner_text(), "and where it is from")
    box = page.locator(".review")
    expect("from the Test imports store" in box.inner_text(), "an imported review names its store")
    expect(box.locator(".actions button").all_inner_texts() == ["Yes", "No"] and page.locator(".map").count() == 0,
           "outside the library, a package the settings name is asked about too (Mathlib on the site), with no map")
    expect(box.locator(".actions a", has_text="Read it in Mathlib's docs").get_attribute("href")
           == "https://leanprover-community.github.io/mathlib4_docs/Init/Data/Int/Basic.html#Int", "and read in Mathlib's docs")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    box.locator(".ai-offer button").click()
    page.wait_for_function("document.querySelector('.ai-offer button').textContent.startsWith('Copied')")
    expect("The site shows it, from the Init that Fixture commit B builds on: https://example.org/#/d/Int"
           in box.locator(".ai-prompt").inner_text(), "its instructions for an AI agent say which version")
    page = visit(browser, url, "#/d/Bool", errors)
    expect(page.locator(".review .actions").count() == 0, "a package the settings do not name is not asked about")


class FakeGitHub:
    """GitHub as the page meets it signing in and filing: its sign-in page sends the reader straight back with a code
    (or, denied, with an error); the helper swaps the code for a token; the API says whose it is, and files issues and
    comments, kept here to look at. `refuse` makes the next filings answer that status instead."""
    CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-GitHub-Api-Version"}

    def __init__(self, page, back_to: str):
        self.back_to, self.deny, self.refuse = back_to, False, None
        self.authorized, self.exchanged, self.issues, self.comments = [], [], [], []
        page.route(re.compile(r"^https://github\.com/login/oauth/authorize\?"), self.authorize)
        page.route("https://signin.example.org/token", self.exchange)
        page.route("https://api.github.com/**", self.api)

    def authorize(self, route):
        q = {k: v[0] for k, v in parse_qs(urlparse(route.request.url).query).items()}
        self.authorized.append(q)
        back = f"error=access_denied&state={q['state']}" if self.deny else f"code=the-code&state={q['state']}"
        route.fulfill(status=302, headers={"Location": f"{self.back_to}?{back}"})

    def exchange(self, route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=self.CORS)
        self.exchanged.append(route.request.post_data_json)
        route.fulfill(status=200, headers=self.CORS, json={"access_token": "ghu_fixture", "token_type": "bearer", "expires_in": 28800})

    def api(self, route):
        req, path = route.request, urlparse(route.request.url).path
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=self.CORS)
        auth = req.headers.get("authorization")
        if path == "/user" and auth == "Bearer ghu_fixture":
            return route.fulfill(status=200, headers=self.CORS, json={"login": "tester"})
        if self.refuse and req.method == "POST":
            return route.fulfill(status=self.refuse, headers=self.CORS, json={"message": "Bad credentials"})
        if path == "/repos/example/fixture-store/issues" and req.method == "POST":
            n = 40 + len(self.issues)
            self.issues.append({"auth": auth, **req.post_data_json})
            return route.fulfill(status=201, headers=self.CORS,
                                 json={"number": n, "html_url": f"https://github.com/example/fixture-store/issues/{n}"})
        m = re.fullmatch(r"/repos/example/fixture-store/issues/(\d+)/comments", path)
        if m and req.method == "POST":
            self.comments.append((int(m.group(1)), req.post_data_json["body"], auth))
            return route.fulfill(status=201, headers=self.CORS, json={"id": 1})
        route.fulfill(status=404, headers=self.CORS, json={"message": "Not Found"})


@check
def signin(browser, url, errors):
    import yaml
    from evidence_store import forms
    fake = {}

    def before(page):
        page.add_init_script("window.__opened = []; window.open = u => { window.__opened.push(u); return null; };")
        fake["gh"] = FakeGitHub(page, url)
    page = visit(browser, url, "#/d/Fixture.triple", errors, before=before)
    gh, box = fake["gh"], page.locator(".review")
    note, shown = box.locator(".sent-note:visible"), box.locator("form.unfold:visible")
    opened = lambda: page.evaluate("window.__opened[window.__opened.length - 1]")
    kept = lambda: page.evaluate("JSON.parse(localStorage.getItem('tauceti-review:github') || 'null')")
    said = lambda pattern: page.wait_for_function(  # in the note showing: each form has its own
        f"[...document.querySelectorAll('.review .sent-note')].some(n => !n.hidden && /{pattern}/.test(n.textContent))", timeout=30000)

    def via_github(button):
        """Off to GitHub (the fake) and back, which loads the page afresh."""
        with page.expect_navigation(wait_until="load", timeout=30000):
            button.click()
        page.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
    issue = lambda i, kind: (gh.issues[i]["title"], gh.issues[i]["labels"], forms.parse(kind, gh.issues[i]["body"]))
    # The forms as the site writes them are the templates' forms: titles, labels, and fields in order.
    site_forms = page.evaluate("TauRender.FORMS")
    for name, f in site_forms.items():
        t = yaml.safe_load((HERE.parent / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8"))
        expect((f["title"], [f["label"]], [tuple(x) for x in f["fields"]])
               == (t["title"], t["labels"], [(b["id"], b["attributes"]["label"]) for b in t["body"] if b["type"] != "markdown"]),
               f"{name}: the site writes an issue as the form does")
    expect(sorted(site_forms) == ["evidence-challenge.yml", "evidence-problem.yml", "evidence-question.yml", "evidence-review.yml"],
           "each form the review box fills in")
    # Signed out: an answer goes to GitHub, filled in; signing in is offered to whoever reviews several.
    how = box.locator("p.how").inner_text()
    expect(how.startswith("Yes and No open a short form here") and "Reviewing several declarations?" in how
           and box.locator("p.how button", has_text="Sign in with GitHub").count() == 1, "signed out, said: GitHub first, signing in for several")
    box.locator(".actions button", has_text="Yes").click()
    offer = shown.locator(".signin-offer")
    expect(shown.count() == 1 and shown.locator("button.send").inner_text() == "Send on GitHub ↗"
           and offer.is_visible() and "Reviewing several declarations?" in offer.inner_text()
           and shown.locator("button", has_text="or send it on GitHub").is_hidden(), "signed out, Yes opens its form, and Send goes to GitHub")
    shown.locator("button.send").click()
    expect(on_github(opened(), "review") == ("Correctly stated: Fixture.triple", "evidence:review", {"decl": "Fixture.triple", "commit": "B"})
           and note.inner_text().startswith("Opened on GitHub"), "and answers on GitHub, filled in")
    box.locator(".actions button", has_text="Yes").click()
    via_github(shown.locator(".signin-offer button", has_text="Sign in with GitHub"))
    # GitHub sends the reader back; the page signs in, and files the yes it was given.
    said("Filed")
    a = gh.authorized[0]
    expect((a["client_id"], a["redirect_uri"], a["code_challenge_method"]) == ("Iv23fixture", "https://example.org/", "S256")
           and len(a["code_challenge"]) == 43 and len(a["state"]) >= 20, "off to GitHub with the app's client ID, a state and PKCE")
    x = gh.exchanged[0]
    verifier = base64.urlsafe_b64encode(hashlib.sha256(x["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    expect(x["code"] == "the-code" and x["redirect_uri"] == "https://example.org/" and verifier == a["code_challenge"],
           "the helper is given the code and the verifier that matches the challenge")
    expect(issue(0, "review") == ("Correctly stated: Fixture.triple", ["evidence:review"], {"decl": "Fixture.triple", "commit": "B"})
           and gh.issues[0]["auth"] == "Bearer ghu_fixture", "the yes is filed as the form files it: intake reads it so")
    expect(page.evaluate("location.search") == "" and page.evaluate("location.hash") == "#/d/Fixture.triple",
           "and the page's address is as it was")
    expect("issue #40" in note.inner_text() and "by @tester" in note.inner_text()
           and note.locator("a[href='https://github.com/example/fixture-store/issues/40']").count() == 1, "it says so, with its issue")
    expect(kept()["login"] == "tester" and kept()["token"] == "ghu_fixture" and "Answering as @tester" in box.locator("p.how").inner_text(),
           "and whom it answers as")
    # Undo: /withdraw on its issue.
    note.locator("button", has_text="Undo").click()
    said("Taken back")
    expect(gh.comments == [(40, "/withdraw", "Bearer ghu_fixture")], "Undo comments /withdraw on the issue")
    # Signed in, Yes is one click.
    box.locator(".actions button", has_text="Yes").click()
    said("issue #41")
    expect(len(gh.issues) == 2 and shown.count() == 0, "signed in, Yes files at once, with no form")
    box.locator(".actions button", has_text="Yes").click()
    expect(len(gh.issues) == 2 and note.count() == 1, "and again says so, filing nothing twice")
    note.locator("button", has_text="Add why").click()
    expect(shown.count() == 1 and shown.locator("label").inner_text() == "Why is it correctly stated?"
           and shown.locator("button.send").is_disabled() and shown.locator(".again").is_visible(), "Add why: the reason is the point")
    shown.locator("textarea").fill("Checked against Stacks.")
    shown.locator("button.send").click()
    said("issue #42")
    expect(issue(2, "review")[2] == {"decl": "Fixture.triple", "commit": "B", "rationale": "Checked against Stacks."},
           "filed again, with why")
    # No, a suggestion, a test: their forms, and Send files them.
    box.locator(".actions button", has_text="No").click()
    expect(shown.locator("button.send").inner_text() == "Send" and shown.locator("button.send").is_disabled(), "No asks why")
    shown.locator("textarea").fill("It is the wrong object.")
    shown.locator("button.send").click()
    said("your no, issue #43")
    expect(issue(3, "problem") == ("Not correctly stated: Fixture.triple", ["evidence:problem"],
                                   {"decl": "Fixture.triple", "commit": "B", "rationale": "It is the wrong object."}), "the no, filed")
    expect(note.locator("button", has_text="Add why").count() == 0 and note.locator("button", has_text="Undo").count() == 1,
           "a no can be taken back too")
    box.locator(".offer button", has_text="Suggest an improvement").click()
    shown.locator("textarea").fill("State it for any semiring.")
    shown.locator("button.send").click()
    said("your suggestion, issue #44")
    expect(issue(4, "question") == ("What could be better: Fixture.triple", ["evidence:question"],
                                    {"decl": "Fixture.triple", "commit": "B", "question": "State it for any semiring."}), "the suggestion")
    box.locator(".offer button", has_text="Suggest a test").click()
    shown.locator("textarea").nth(0).fill("its value at 0")
    shown.locator("textarea").nth(1).fill("triple 0 = 0")
    shown.locator("textarea").nth(2).fill("a definition off by one")
    shown.locator("button.send").click()
    said("your test, issue #45")
    expect(issue(5, "challenge") == ("Suggested test: Fixture.triple", ["evidence:challenge"],
                                     {"decl": "Fixture.triple", "commit": "B", "property": "its value at 0", "statement": "triple 0 = 0",
                                      "catches": "a definition off by one"}), "the test")
    box.locator(".actions button", has_text="No").click()
    shown.locator("textarea").fill("Off by one.")
    shown.locator("button", has_text="or send it on GitHub").click()
    expect(on_github(opened(), "problem")[2] == {"decl": "Fixture.triple", "commit": "B", "rationale": "Off by one."}
           and len(gh.issues) == 6, "signed in, it still opens on GitHub if asked")
    # A sign-in that has ended: say so, sign in again, and file it then.
    gh.refuse = 401
    box.locator(".actions button", has_text="No").click()
    shown.locator("textarea").fill("Off by two.")
    shown.locator("button.send").click()
    said("sign-in has ended")
    expect(kept() is None, "an ended sign-in is forgotten")
    gh.refuse = None
    via_github(note.locator("button", has_text="Sign in with GitHub and send"))
    said("your no, issue #46")
    expect(issue(6, "problem")[2]["rationale"] == "Off by two." and len(gh.authorized) == 2, "signed in again, the no is filed")
    # Sign out.
    box.locator("p.how button", has_text="Sign out").click()
    expect(kept() is None and box.locator("p.how").inner_text().startswith("Yes and No open a short form here"), "Sign out forgets the sign-in")
    # GitHub not given access: back with the answer, and another way to send it.
    gh.deny = True
    box.locator(".actions button", has_text="Yes").click()
    via_github(shown.locator(".signin-offer button", has_text="Sign in with GitHub"))
    said("not given access")
    expect(shown.count() == 1 and note.locator("button", has_text="Send it on GitHub instead").count() == 1
           and len(gh.exchanged) == 2 and len(gh.issues) == 7, "denied: said, nothing filed, and GitHub's form offered")
    # A reply GitHub did not send (no sign-in under way here, or another state) is not used.
    page.goto(url + "?code=forged&state=forged#/d/Fixture.triple", wait_until="load")
    settle(page, "decl:Fixture.triple")
    expect(len(gh.exchanged) == 2 and kept() is None and page.evaluate("location.search") == "", "a forged reply is not used")
    # A sign-in whose token has ended counts as none.
    page.evaluate("localStorage.setItem('tauceti-review:github', JSON.stringify({token: 'ghu_old', login: 'tester', expires: Date.now() - 1}))")
    page.reload(wait_until="load")
    settle(page, "decl:Fixture.triple")
    expect(page.locator(".review p.how").inner_text().startswith("Yes and No open a short form here"), "an ended sign-in shows as signed out")
    errors[:] = [e for e in errors if "status of 401" not in e]  # the browser's own line for the 401 above, asked for


@check
def reviewed(browser, url, errors):
    page = visit(browser, url, "#/reviewed", errors)
    expect(page.locator("h1").inner_text() == "Reviewed" and page.locator(".nav a.on").inner_text() == "Reviewed", "the Reviewed page")
    items = page.locator(".list > li")
    expect(items.count() == 11, "every declaration answered for")
    expect(page.locator(".list a[href='#/d/Int'] .answers .badge").inner_text() == "Init", "one outside the library, its package said")
    first = items.first
    expect(first.locator(".item-sub").inner_text() == "Fixture.triple_comm", "the latest answer first")
    expect(first.locator(".answer.yes").count() == 1 and first.locator(".answer.no").count() == 1, "with its yes and its no")
    page.click("[data-answer=no]")
    expect(page.locator(".list > li").count() == 1, "the noes still open")
    page.click("[data-answer=yes]")
    expect(page.locator(".list > li").count() == 6, "the yeses")
    page.select_option("select[aria-label='Answered by']", "ai")
    expect(page.locator(".list .item-sub").all_inner_texts() == ["Fixture.triple"], "the AI agents' yeses")
    expect(page.locator(".list .answer.yes").text_content() == "✓1 AI", "counted as AI")
    page.click(".list > li a")
    settle(page, "decl:Fixture.triple")
    expect(page.locator(".review .mark.tally.yes").count() == 1, "an item opens its declaration")


@check
def formulas(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    doc = "The theta series `Θ_L(τ) = ∑_{v ∈ L} exp (π i ‖v‖² τ)` of `L : Submodule ℤ E` (`ZLattice.summable_thetaSeries`)."
    said = "Θ_L(τ) = Σ_{v∈L} exp(πi‖v‖²τ) for a lattice L; both converge on ℍ (Serre, *A Course in Arithmetic*, VII §6)."
    got = page.evaluate("""texts => texts.map(t => { const b = TauRender.md(t);
        return {math: b.querySelectorAll('math').length, code: [...b.querySelectorAll('code')].map(c => c.textContent),
                em: [...b.querySelectorAll('em')].map(e => e.textContent)}; })""", [doc, said])
    expect(got[0]["math"] == 1 and got[0]["code"] == ["L : Submodule ℤ E", "ZLattice.summable_thetaSeries"],
           "a docstring's formula typeset, its Lean left as code")
    expect(got[1]["math"] == 1 and got[1]["em"] == ["A Course in Arithmetic"], "Voyager's formula typeset, its underscores not emphasis")


@check
def dependency_map(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    map_drawn(page)
    names = page.evaluate("TauReview.mapNodes()")
    expect("Fixture.triple" in names and "Nat" not in names, "what it rests on in the library, Mathlib hidden")
    expect(page.locator(".map .node.k-concept[data-name='Fixture.triple']").count() == 1, "a node in its kind's colour")
    # Fixture.triple rests on nothing else of the library: no arrow offers to unfold it.
    expect(page.locator(".map .node[data-name='Fixture.triple'] .open").count() == 0, "no arrow where there is nothing to unfold")
    page.click(".map-tools button:has-text('Full screen')")
    expect(page.locator(".map.full").count() == 1 and page.locator(".map-tools button", has_text="Leave full screen").is_visible(),
           "full screen says how to leave it")
    page.keyboard.press("Escape")
    expect(page.locator(".map.full").count() == 0 and page.locator(".map-tools button", has_text="Full screen").is_visible(), "Esc leaves it")
    page.click(".map-tools button:has-text('Full screen')")
    page.click(".map-tools button:has-text('Leave full screen')")
    expect(page.locator(".map.full").count() == 0, "and so does its button")
    node = page.locator(".map .node[data-name='Fixture.triple'] rect")
    node.scroll_into_view_if_needed()
    box = node.bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 70, box["y"] + 50, steps=5)
    page.mouse.up()
    page.wait_for_timeout(800)
    expect(page.evaluate("TauReview.route()") == "decl:Fixture.triple_pos", "a drag that starts on a node does not open it")
    page.click(".map-tools button:has-text('Mathlib')")
    page.wait_for_function("TauReview.mapNodes().includes('Nat')")
    names = page.evaluate("TauReview.mapNodes()")
    expect("OfNat" not in names and "LT" not in names, "Lean's plumbing left out: the classes behind notation")
    page.click(".map .node[data-name='Fixture.triple'] rect")
    settle(page, "decl:Fixture.triple")
    page.wait_for_selector(".map .node[data-name='Fixture.triple_pos']")
    # With proofs an arrow is a guess: one that finds nothing says so, and goes.
    page.click(".map-tools button:has-text('Proof uses')")
    leaf = ".map .node[data-name='Fixture.triple_two'] .open"
    page.wait_for_selector(leaf)
    page.click(leaf)
    page.wait_for_selector(".map-note.on")
    expect("Nothing else in Fixture rests on" in page.inner_text(".map-note") and page.locator(leaf).count() == 0
           and page.evaluate("TauReview.route()") == "decl:Fixture.triple", "an arrow that finds nothing says so, and goes")
    page = visit(browser, url, "#/d/Fixture.one", errors)
    page.wait_for_selector(".map .node[data-name]")
    expect("Fixture.one_pos'" not in page.evaluate("TauReview.mapNodes()"), "proofs left out at first")
    page.click(".map-tools button:has-text('Proof uses')")
    page.wait_for_function("TauReview.mapNodes().includes(\"Fixture.one_pos'\")")
    # Resting on nothing of the library, a map opens on what it rests on outside it, plumbing aside (asked for on
    # 2026-10-26: the Kronecker symbol's map was empty above it).
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    page.wait_for_function("TauReview.mapNodes().includes('Nat')")
    expect(page.locator(".map-tools button", has_text="Mathlib").get_attribute("aria-pressed") == "true", "with the Mathlib layer on")
    names = page.evaluate("TauReview.mapNodes()")
    expect("HAdd" not in names and "outParam" not in names, "and without Lean's plumbing")


@check
def other_pages(browser, url, errors):
    page = visit(browser, url, "#/m/Fixture.Uses", errors)
    expect(page.locator(".list > li").count() >= 4, "a module lists its declarations")
    page = visit(browser, url, "#/area/Basic", errors)
    expect(page.locator(".list a[href^='#/m/']").count() == 1 and page.locator(".list a[href^='#/d/']").count() == 1,
           "an area: its files and its named")
    page = visit(browser, url, "#/browse", errors)
    expect(page.locator("a.card").count() == 3, "Browse: a tile for each area")
    page = visit(browser, url, "#/activity", errors)
    expect("double n = n + n" in page.locator(".section", has_text="Suggested tests").inner_text(), "the open suggested test")
    better = page.locator(".section", has=page.locator("h2", has_text="What could be better"))
    expect("any semiring" in better.inner_text(), "the open suggestions")
    answered = page.locator(".section", has=page.locator("h2", has_text="Answered no, resolved"))
    fold = answered.locator(".thread details.twisty.fold")
    expect(answered.locator("a.decl-link").all_inner_texts() == ["Fixture.one"] and fold.count() == 1
           and not fold.evaluate("d => d.open") and "Behaves as intended" in fold.locator("summary").inner_text(),
           "each no answered, folded: where it stands and who said it")
    fold.locator("summary").click()
    expect(fold.locator(".resolution", has_text="Behaves as intended").locator(".md p").count() == 2
           and fold.locator(".resolution .md p").first.is_visible(), "which opens to why, in full")
    page = visit(browser, url, "#/d/Fixture.one", errors)
    box = page.locator(".review")
    settled = box.locator(".answers-list .mark.yes.resolved")
    expect(settled.count() == 1 and "behaves as intended" in settled.inner_text() and settled.locator(".tick").inner_text() == "✓"
           and box.locator(".answers-list .mark.no").count() == 0 and box.locator(".mark.tally.no").count() == 0,
           "a no decided in its favour is a green tick, saying how, and no cross is left")
    report = page.locator(".review details.report.twisty.closed")
    expect(report.locator("summary .state").inner_text() == "Behaves as intended" and not report.evaluate("d => d.open"),
           "a no answered, folded into a line saying how it stands")
    report.locator("summary").click()
    expect(report.locator(".resolution").count() == 2
           and report.locator(".resolution").last.locator(".md p").all_inner_texts()
           == ["Pos admits 0 on purpose: it is the predicate, and the theorems about it assume 0 < n where they need it.",
               "With that usual hypothesis it is the positive integers, so the declaration says what it should."],
           "which opens to how, by whom, and why, in full")
    page = visit(browser, url, "#/help", errors)
    expect("Reviewed-by: TauCeti.Foo.bar" in page.inner_text("body"), "the bulk issue's lines")
    expect(page.locator("a[href='https://github.com/example/fixture-store/blob/main/AI-REVIEWS.md']").count() == 1
           and "Review TauCeti.Foo.bar for the Tau Ceti review site" in page.inner_text("body"), "how to ask an AI agent for a review")


@check
def phone(browser, url, errors):
    for route in ("#/d/Fixture.triple_pos", "#/named", "#/reviewed"):
        page = visit(browser, url, route, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        expect(page.locator("#q").is_visible() and page.locator(".nav a").first.is_visible(), "search and the sections at the top")
        expect(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{route}: nothing is wider than the screen")


def map_drawn(page) -> None:
    """Waits for the map to be drawn: nodes, or the sentence that says there are none."""
    page.wait_for_function("document.querySelector('.map .node[data-name]') || [...document.querySelectorAll('.map-wait')]"
                           ".some(e => !e.textContent.startsWith('Drawing'))", timeout=60000)


def smoke(browser, url, errors):
    """Any build: every kind of page opens, and the first named declarations draw their maps."""
    for route in ("#/", "#/named", "#/reviewed", "#/browse", "#/activity", "#/help", "#/search/theorem"):
        visit(browser, url, route, errors)
    page = visit(browser, url, "#/named", errors)
    expect(page.locator("h1").inner_text() == "Named results and notable definitions", "the Named page")
    first = "as => as.slice(0, 5).map(a => decodeURIComponent(a.hash.slice(4)))"
    names = page.eval_on_selector_all(".list > li > a", first)
    if not names:  # Voyager's announcements not recorded yet: declarations found by a search instead
        page = visit(browser, url, "#/search/theorem", errors)
        names = page.eval_on_selector_all(".list > li > a", first)
    expect(len(names) == 5, "five declarations to open")
    for name in names:
        page = visit(browser, url, "#/d/" + name, errors)
        map_drawn(page)
        expect(page.locator("h1").count() == 1 and page.locator(".review .actions button").count() == 2,
               f"{name}: its page and its question's two answers")
        # What the reader sees is the signature the site's data has, character for character: the docs' own
        # header where they have one (scripts/docs_signatures.py), each checked against the docs before the
        # dataset is published (scripts/check_signatures.py).
        kw, sig = page.evaluate("async n => { const d = await TauData.decl(n); return [d.entry.kw || '', d.entry.sig || '']; }", name)
        if sig:
            shown = " ".join(page.locator(".lean pre").first.inner_text().split())
            expect(shown == " ".join(f"{kw} {sig}".split()), f"{name}: its signature shown as the dataset has it")
        arrow = page.locator(".map .node .open:not(.opened)")
        if arrow.count():  # an arrow unfolds something, or says it found nothing
            before = page.locator(".map .node").count()
            arrow.first.dispatch_event("click")
            page.wait_for_function(f"document.querySelectorAll('.map .node').length > {before} || document.querySelector('.map-note.on')")
        page = visit(browser, url, "#/d/" + name, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        expect(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{name}: nothing is wider than a phone")
    outside_statements(browser, url, errors)


def outside_statements(browser, url, errors):
    """A declaration outside the library that someone reviewed shows its statement too (`zero_smul` showed
    none on 2026-10-26), as the site's data has it."""
    page = visit(browser, url, "#/", errors)
    for name in page.evaluate("async () => Object.keys(await TauData.upstream()).slice(0, 2)"):
        page = visit(browser, url, "#/d/" + name, errors)
        kw, sig = page.evaluate("async n => { const d = await TauData.decl(n); return [d.entry ? d.entry.kw || '' : '', d.entry ? d.entry.sig || '' : '']; }", name)
        expect(bool(sig), f"{name}: a statement outside the library")
        shown = " ".join(page.locator(".lean pre").first.inner_text().split())
        expect(shown == " ".join(f"{kw} {sig}".split()), f"{name}: its statement shown as the site's data has it")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="validate_site.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path)
    ap.add_argument("--url")
    ap.add_argument("--only", default="")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(argv)
    site = a.site
    if site is None and a.url is None:
        sys.path.insert(0, str(HERE))
        import fixture_site
        site = Path(tempfile.mkdtemp(prefix="site-check-")) / "site"
        fixture_site.build(site)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser closed a page while a file was on its way
    server = None
    if a.url:
        url = a.url.rstrip("/") + "/index.html"
    else:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    checks = {"smoke": smoke} if a.smoke else CHECKS
    names = [n for n in checks if not a.only or n in a.only.split(",")]
    failed = False
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names:
            errors: list = []
            try:
                checks[name](browser, url, errors)
                if errors:
                    raise Fail(f"errors in the page: {errors[:3]}")
                print(f"ok    {name}")
            except Exception as e:  # a failed check, a timeout, or the page's own error
                failed = True
                print(f"FAIL  {name}: {e}")
        browser.close()
    if server:
        server.shutdown()
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
