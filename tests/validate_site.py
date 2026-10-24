#!/usr/bin/env python3
"""The browser check: serves a built site as GitHub Pages would and checks, in Chromium, what a
reader does: the shell and its two themes, the old addresses, the home page, the Named page, search,
a declaration, its review box, formulas typeset, its dependency map, the other pages, and a phone. Without --site it
builds the fixture's site first (tests/fixture_site.py).

  python3 tests/validate_site.py [--site DIR | --url URL] [--only NAME,NAME] [--smoke]

`--smoke` checks a real build instead of the fixture's (`--site _site`, or the published site with
`--url`): the pages open without errors, and the first named declarations draw their maps.
Prints one line per check, then PASS (exit 0) or FAIL (exit 1). Errors in the page's console fail
the check that met them.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
import tempfile
import threading
from pathlib import Path

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


def visit(browser, url: str, route: str, errors: list, **context):
    page = browser.new_context(**({"viewport": {"width": 1440, "height": 900}} | context)).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(url + route, wait_until="load")
    page.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
    return page


def settle(page, route: str) -> None:
    page.wait_for_function(f"TauReview.route() === {route!r} && TauReview.ready", timeout=30000)


@check
def shell(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    expect(page.locator(".brand").inner_text().strip() == "Tau Ceti Review", "the top bar names the site")
    expect(page.locator(".nav a").all_inner_texts() == ["Named", "Browse", "Activity", "How to review"], "and its sections")
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
    expect(page.locator(".stat").count() == 5 and page.locator("a.card").count() == 4, "its counts and its tiles")
    expect(page.locator(".section", has_text="Latest named").locator(".list > li").count() == 2, "the latest named")
    expect(page.locator(".section", has_text="Areas").locator("a.chip").count() == 3, "the areas")


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
    hrefs = page.eval_on_selector_all(".links a", "as => as.map(a => a.href)")
    expect("https://example.org/docs/Fixture/Basic.html#Fixture.triple" in hrefs, "the API docs")
    expect("https://github.com/test/fixture/blob/B/Fixture/Basic.lean#L15-L16" in hrefs, "the source at the pin")
    expect(page.locator("h2", has_text="Results about it").count() == 1, "what rests on it, as a list")
    expect(page.locator(".list > li", has_text="triple 2 = 6").count() == 1, "each result in a list with its statement")
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    expect(page.locator(".lean pre").first.inner_text() == "theorem Fixture.triple_pos (n : Nat) (h : 0 < n) : 0 < Fixture.triple n",
           "a theorem's signature, section variables and all")
    ref = page.locator(".lean a.ref", has_text="Fixture.triple")
    expect(ref.get_attribute("href") == "#/d/Fixture.triple", "its names link")
    expect(page.locator(".lean details").count() == 0 and "omega" not in page.inner_text("main"), "no proof")
    about = page.locator(".section", has=page.locator("h2", has_text="What it is about"))
    expect(about.locator(".list > li").count() == 1 and "natural numbers ℕ" in about.locator(".basics").inner_text(),
           "what it rests on in the library listed, what it uses from Mathlib and Lean as chips")
    ref.hover()
    page.wait_for_selector("#tip:not([hidden])")
    expect("Fixture.triple · Definition" in page.locator("#tip").inner_text(), "a name says what it is on hover")


@check
def review(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    box = page.locator(".review")
    tally = box.locator(".mark.tally").first
    expect(tally.locator(".trailer").inner_text() == "Reviewed-by" and tally.locator(".who").inner_text() == "1 person · 1 AI",
           "people are counted apart from AI agents")
    expect(box.locator("details.whose .mark.person").count() == 1 and box.locator("details.whose .mark.agent .ai").count() == 1,
           "in Who, each reviewer's mark, the AI agent's marked")
    expect(box.locator("details.whose .mark.agent").get_attribute("href") == "https://github.com/example/fixture-store/issues/11",
           "a mark opens its review's issue")
    href = box.locator(".actions a", has_text="Review this").get_attribute("href")
    expect(href.startswith("https://github.com/example/fixture-store/issues/new?") and "template=evidence-review.yml" in href
           and "decl=Fixture.triple" in href and "commit=B" in href, "Review this opens the form, filled in")
    expect(box.locator(".actions a[href*='/issues/new?']").all_inner_texts()
           == ["Review this", "Suggest a test", "Report a problem", "List a test", "Ask a question"], "a button for each form")
    expect(box.locator(".actions a", has_text="Read it in the API docs").get_attribute("href")
           == "https://example.org/docs/Fixture/Basic.html#Fixture.triple", "the review box links to the docs")
    expect(box.locator(".mark.tally.tested").count() == 1 and box.locator(".which .pass").count() == 1, "Tested by: the listed test passes")
    page = visit(browser, url, "#/d/Fixture.double_zero", errors)
    expect("what it rests on has changed" in page.locator(".review details.whose").inner_text(), "stale underneath, said")
    page = visit(browser, url, "#/d/Fixture.double", errors)
    box = page.locator(".review")
    expect(box.locator("details.whose .mark.stale").count() == 1 and "1 on an earlier version" in box.inner_text(),
           "a review of an earlier version, greyed")
    expect(box.locator(".which .test", has_text="Suggested by").count() == 1, "the open suggested test")
    page = visit(browser, url, "#/d/Int", errors)
    expect("from the Test imports store" in page.locator(".review").inner_text(), "an imported review names its store")
    expect(page.locator(".actions").count() == 0 and page.locator(".map").count() == 0, "no forms and no map outside the library")


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
    page = visit(browser, url, "#/help", errors)
    expect("Reviewed-by: TauCeti.Foo.bar" in page.inner_text("body"), "the bulk issue's lines")
    expect(page.locator("a[href='https://github.com/example/fixture-store/blob/main/AI-REVIEWS.md']").count() == 1
           and "Review TauCeti.Foo.bar for the Tau Ceti review site" in page.inner_text("body"), "how to ask an AI agent for a review")


@check
def phone(browser, url, errors):
    for route in ("#/d/Fixture.triple_pos", "#/named"):
        page = visit(browser, url, route, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        expect(page.locator("#q").is_visible() and page.locator(".nav a").first.is_visible(), "search and the sections at the top")
        expect(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{route}: nothing is wider than the screen")


def map_drawn(page) -> None:
    """Waits for the map to be drawn: nodes, or the sentence that says there are none."""
    page.wait_for_function("document.querySelector('.map .node[data-name]') || [...document.querySelectorAll('.map-wait')]"
                           ".some(e => !e.textContent.startsWith('Drawing'))", timeout=60000)


def smoke(browser, url, errors):
    """Any build: every kind of page opens, and the first named declarations draw their maps."""
    for route in ("#/", "#/named", "#/browse", "#/activity", "#/help", "#/search/theorem"):
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
        expect(page.locator("h1").count() == 1 and page.locator(".review .actions a[href*='/issues/new?']").count() == 5,
               f"{name}: its page and its forms")
        arrow = page.locator(".map .node .open:not(.opened)")
        if arrow.count():  # an arrow unfolds something, or says it found nothing
            before = page.locator(".map .node").count()
            arrow.first.dispatch_event("click")
            page.wait_for_function(f"document.querySelectorAll('.map .node').length > {before} || document.querySelector('.map-note.on')")
        page = visit(browser, url, "#/d/" + name, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        expect(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{name}: nothing is wider than a phone")


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
