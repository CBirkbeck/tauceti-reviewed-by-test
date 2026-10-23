#!/usr/bin/env python3
"""The browser check: serves a built site as GitHub Pages would and checks, in Chromium, what a
reader does: the shell, the old addresses, the Named page, search, a declaration, its review panel,
its dependency map, the other pages, and a phone. Without --site it builds the fixture's site first
(tests/fixture_site.py).

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
    expect(page.locator(".brand").inner_text().strip() == "Tau Ceti Review", "the header names the site")
    expect(page.locator("#rail-areas .nav-item").count() == 3, "the rail lists the three areas")
    expect("@ B" in page.locator("#pin").inner_text(), "the header names the pinned commit")
    expect(page.evaluate("[TauReview.fnv('TauCeti.Place', 64), TauReview.fnv('Fixture.«term𝟚_»', 64), TauReview.fnv('ℝ', 64)]")
           == [47, 38, 8], "the page shards names as scripts/common.py does")


@check
def old_addresses(browser, url, errors):
    page = visit(browser, url, "#d=Fixture.double", errors)
    expect(page.evaluate("location.hash") == "#/d/Fixture.double", "#d= opens the declaration")
    page = visit(browser, url, "#q=triple", errors)
    expect(page.evaluate("location.hash") == "#/search/triple", "#q= searches")


@check
def named(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    expect(page.locator(".card").count() == 2, "both announcements are listed")
    page.click("[data-what=definition]")
    expect(page.locator(".card").count() == 1 and "Being double" in page.locator(".card").inner_text(), "the definitions filter")
    page.click(".card .card-title")
    settle(page, "decl:Fixture.IsDouble")
    expect(page.locator("h1").inner_text() == "Being double", "a card opens its declaration, titled by Voyager")


@check
def search(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    page.fill("#q", "triple")
    settle(page, "search:triple")
    expect(page.locator(".nitem .n").first.inner_text().startswith("Fixture.triple"), "a name finds its declarations")
    page.fill("#q", "leaves alone")
    settle(page, "search:leaves alone")
    expect("Fixture.triple" in page.locator(".nitem .n").all_inner_texts(), "words from a title find it")


@check
def declaration(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    expect(page.locator("h1").inner_text() == "A definition that version B leaves alone.", "titled by its docstring")
    expect("def triple (n : Nat) : Nat" in page.locator(".lean pre").first.inner_text(), "its source")
    hrefs = page.eval_on_selector_all(".links a", "as => as.map(a => a.href)")
    expect("https://example.org/docs/Fixture/Basic.html#Fixture.triple" in hrefs, "the API docs")
    expect("https://github.com/test/fixture/blob/B/Fixture/Basic.lean#L15-L16" in hrefs, "the source at the pin")
    expect(page.locator("h2", has_text="Results about it").count() == 1, "what rests on it, as a list")
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    expect(page.locator("details summary", has_text="Proof").count() == 1, "a theorem's proof is folded")


@check
def review(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    expect("1 person · 1 AI" in page.locator(".state-line").inner_text(), "people are counted apart from AI agents")
    href = page.locator(".actions a", has_text="Review this").get_attribute("href")
    expect(href.startswith("https://github.com/example/fixture-store/issues/new?") and "template=evidence-review.yml" in href
           and "decl=Fixture.triple" in href and "commit=B" in href, "Review this opens the form, filled in")
    expect(page.locator(".actions a").count() == 5, "five forms")
    expect(page.locator(".tests .result.passes").count() == 1, "the listed test passes")
    page = visit(browser, url, "#/d/Fixture.double_zero", errors)
    expect("Something it rests on has changed since." in page.locator(".panel").inner_text(), "stale underneath, said")
    page = visit(browser, url, "#/d/Fixture.double", errors)
    panel = page.locator(".panel").inner_text()
    expect("The declaration has changed since." in panel, "stale, said")
    expect(page.locator(".verdict.challenge").count() == 1 and "Open" in panel, "the open suggested test")
    page = visit(browser, url, "#/d/Int", errors)
    expect("From the Test imports store" in page.locator(".panel").inner_text(), "an imported review names its store")
    expect(page.locator(".actions").count() == 0 and page.locator(".map").count() == 0, "no forms and no map outside the library")


@check
def dependency_map(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    map_drawn(page)
    names = page.evaluate("TauReview.mapNodes()")
    expect("Fixture.triple" in names and "Nat" not in names, "what it rests on in the library, Mathlib hidden")
    page.click(".map-tools button:has-text('Mathlib')")
    page.wait_for_function("TauReview.mapNodes().includes('Nat')")
    page.click(".map .node[data-name='Fixture.triple'] rect")
    settle(page, "decl:Fixture.triple")
    page.wait_for_selector(".map .node[data-name='Fixture.triple_pos']")
    page = visit(browser, url, "#/d/Fixture.one", errors)
    page.wait_for_selector(".map .node[data-name]")
    expect("Fixture.one_pos'" not in page.evaluate("TauReview.mapNodes()"), "proofs left out at first")
    page.click(".map-tools button:has-text('Proof uses')")
    page.wait_for_function("TauReview.mapNodes().includes(\"Fixture.one_pos'\")")


@check
def other_pages(browser, url, errors):
    page = visit(browser, url, "#/m/Fixture.Uses", errors)
    expect(page.locator(".nitem").count() >= 4, "a module lists its declarations")
    page = visit(browser, url, "#/area/Basic", errors)
    expect(page.locator(".mitem").count() == 1 and page.locator(".card").count() == 1, "an area: its modules and named")
    page = visit(browser, url, "#/activity", errors)
    expect("double n = n + n" in page.locator(".block", has_text="Suggested tests").inner_text(), "the open suggested test")
    page = visit(browser, url, "#/help", errors)
    expect("Reviewed-by: TauCeti.Foo.bar" in page.inner_text("body"), "the bulk issue's lines")


@check
def phone(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors, viewport={"width": 390, "height": 844},
                 is_mobile=True, has_touch=True)
    expect(not page.locator("#rail").is_visible(), "the rail is folded away")
    page.click("#rail-toggle")
    expect(page.locator("#rail").is_visible(), "Browse opens it")
    expect(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "nothing is wider than the screen")


def map_drawn(page) -> None:
    """Waits for the map to be drawn: nodes, or the sentence that says there are none."""
    page.wait_for_function("document.querySelector('.map .node[data-name]') || [...document.querySelectorAll('.map-wait')]"
                           ".some(e => !e.textContent.startsWith('Drawing'))", timeout=60000)


def smoke(browser, url, errors):
    """Any build: every kind of page opens, and the first named declarations draw their maps."""
    for route in ("#/", "#/browse", "#/activity", "#/help", "#/search/theorem"):
        visit(browser, url, route, errors)
    page = visit(browser, url, "#/", errors)
    names = page.eval_on_selector_all(".card .card-title", "as => as.slice(0, 5).map(a => decodeURIComponent(a.hash.slice(4)))")
    expect(len(names) == 5, "the Named page lists announcements")
    for name in names:
        page = visit(browser, url, "#/d/" + name, errors)
        map_drawn(page)
        expect(page.locator("h1").count() == 1 and page.locator(".actions a").count() == 5, f"{name}: its page and its forms")


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
