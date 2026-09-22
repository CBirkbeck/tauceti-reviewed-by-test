"""Browser checks for the search page (scripts/build_site.py).

Serves site/ as GitHub Pages would and checks what a reader does: search by
name and by docstring, filter definitions, open a declaration and review it,
follow a link to one, and read it on a phone. Build the site first:

  python3 scripts/fetch_declarations.py --clone <Tau Ceti checkout>
  python3 scripts/build_site.py
  python3 tests/validate_site.py [screenshot folder]

Prints PASS and exits 0, or names the failed check and exits 1.
"""
from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1] / "site"


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    passed, errors = [], []

    def check(name, value):
        if not value:
            raise AssertionError(name)
        passed.append(name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="load")
            page.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
            check("the overview lists the areas", page.locator(".areas button").count() >= 10)
            if shots:
                page.screenshot(path=str(shots / "site-overview.png"))
            page.fill("#search", "vonMangoldt")
            page.wait_for_timeout(400)
            names = page.evaluate("TauReview.results()")
            check("a name finds its declarations, the closest first", names and names[0].split(".")[-1].lower().startswith("vonmangoldt"))
            page.fill("#search", "Frobenius element")
            page.wait_for_timeout(400)
            check("words from a docstring find declarations", len(page.evaluate("TauReview.results()")) > 0)
            page.click("[data-group='def']")
            page.wait_for_timeout(300)
            kinds = page.evaluate("Array.from(document.querySelectorAll('.result .kw')).map(e => e.textContent)")
            check("the definitions filter shows only definitions", kinds and all(k in ("def", "abbrev", "structure", "class", "inductive", "instance") for k in kinds))
            page.locator(".result").first.click()
            page.wait_for_selector("#panel pre", timeout=15000)
            href = page.locator("#panel a.primary").get_attribute("href")
            check("a declaration opens with its source and a review link", "template=reviewed-by.yml" in href and "declaration=" in href and "version=" in href)
            check("its module's other declarations are listed", page.locator("#panel .siblings button").count() >= 1)
            if shots:
                page.screenshot(path=str(shots / "site-declaration.png"))
            name = page.evaluate("TauReview.state().d")
            other = browser.new_page(viewport={"width": 1440, "height": 900})
            other.on("pageerror", lambda error: errors.append(str(error)))
            other.goto(url + "#d=" + name, wait_until="load")
            other.wait_for_selector("#panel pre", timeout=30000)
            check("a link to a declaration opens it", name in other.locator("#panel h2").inner_text().replace("\n", ""))
            phone = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            phone.on("pageerror", lambda error: errors.append(str(error)))
            phone.goto(url, wait_until="load")
            phone.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
            phone.fill("#search", "absNorm")
            phone.wait_for_timeout(400)
            phone.locator(".result").first.tap()
            phone.wait_for_selector("#panel pre", timeout=15000)
            check("on a phone a declaration fills the screen", phone.evaluate("document.body.classList.contains('reading')") and phone.locator("#panel").is_visible())
            check("and nothing overflows sideways", phone.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
            if shots:
                phone.screenshot(path=str(shots / "site-phone.png"))
            phone.locator("#back").tap()
            phone.wait_for_timeout(300)
            check("back returns to the results", not phone.evaluate("document.body.classList.contains('reading')") and phone.locator(".result").count() > 0)
            # A problem report, added to the page's data in flight so the ledger
            # stays real: flagged, listed by the filter, shown with its issue.
            reported = "TauCeti.IdealArithmeticFunction.vonMangoldt"

            def inject(route):
                response = route.fetch()
                body = response.json()
                entry = body["declarations"].setdefault(reported, {"hash": "", "kind": "def", "url": "", "marks": []})
                entry["problems"] = [{"issue": 999, "status": "open", "what": "wrong", "why": "A test report: it misses the prime powers.",
                                      "fix": "", "by": "tester", "kind": "person", "agent": "", "hash": entry["hash"], "current": True,
                                      "at": "2026-09-22T15:00:00Z"}]
                # Seventeen marks: the page should count them and keep the names one click away.
                entry["marks"] = ([{"trailer": "Reviewed-by", "by": f"person{n}", "kind": "person", "agent": "", "hash": entry["hash"],
                                    "current": True, "at": "2026-09-22T15:00:00Z", "evidence": "", "issue": 1} for n in range(12)]
                                  + [{"trailer": "Reviewed-by", "by": "someone", "kind": "agent", "agent": f"Agent {n}", "hash": entry["hash"],
                                      "current": True, "at": "2026-09-22T15:00:00Z", "evidence": "Checked.", "issue": 1} for n in range(5)])
                entry["tally"] = {"Reviewed-by": {"people": 12, "ai": 5, "earlier": 0}}
                # A unit test, a key result and a suggested test.
                entry["tests"] = {
                    "unit": [{"statement": "example : vonMangoldt (K := ℚ) 1 = 0", "path": "TauCeti/X.lean", "line": 5, "url": "u", "passes": True}],
                    "results": [{"test": "TauCeti.IdealArithmeticFunction.vonMangoldt_one", "status": "passes", "statement": "theorem vonMangoldt_one : vonMangoldt 1 = 0",
                                 "url": "u", "checks": "The unit ideal gets 0.", "by": "someone", "kind": "agent", "agent": "Agent 1", "at": "2026-09-22T15:00:00Z"}],
                    "suggested": [{"issue": 998, "status": "open", "test": "At a prime ideal it is log N(P).", "catches": "", "by": "tester", "kind": "person",
                                   "agent": "", "at": "2026-09-22T15:00:00Z"}],
                    "tally": {"unit": 1, "results": 1, "suggested": 1}}
                route.fulfill(response=response, json=body)
            flagged = browser.new_page(viewport={"width": 1440, "height": 900})
            flagged.on("pageerror", lambda error: errors.append(str(error)))
            flagged.route("**/reviews.json", inject)
            flagged.goto(url, wait_until="load")
            flagged.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
            check("the overview lists open problems", "Open problems" in flagged.locator("#results").text_content())
            flagged.select_option("#state-filter", "tested")
            flagged.wait_for_timeout(300)
            check("the Tested filter finds declarations whose examples in Tau Ceti test them", len(flagged.evaluate("TauReview.results()")) > 10)
            flagged.select_option("#state-filter", "problem")
            flagged.wait_for_timeout(300)
            check("the reported problems filter lists the reported declaration", flagged.evaluate("TauReview.results()") == [reported])
            check("a reported declaration is flagged in the results", flagged.locator(".result .flag").count() == 1)
            flagged.locator(".result").first.click()
            flagged.wait_for_selector("#panel .problem", timeout=15000)
            check("its page shows the report and links to its issue", "misses the prime powers" in flagged.locator("#panel .problem").inner_text()
                  and flagged.locator("#panel .problem a[href$='/issues/999']").count() == 1)
            check("many marks are counted, people apart from AI agents",
                  "12 people · 5 AI" in flagged.locator("#panel .mark.summary").first.text_content())
            check("the names are folded away", not flagged.evaluate("document.querySelector('#panel details.who').open"))
            flagged.locator("#panel details.who summary").click()
            check("one click shows who gave each mark", flagged.locator("#panel details.who .mark").count() == 17)
            check("its tests are counted", "1 unit test · 1 key result · 1 suggested" in flagged.locator("#panel .mark.tested").text_content())
            check("each test shows its statement and whether it passes",
                  flagged.locator("#panel details.which .test").count() == 3 and flagged.locator("#panel details.which .pass").count() == 2)
            suggest = flagged.locator("#panel a[href*='template=test.yml']").get_attribute("href")
            check("a declaration offers Suggest a test, filled in", "declaration=" in suggest and "version=" in suggest)
            report = flagged.locator("#panel a.warn").get_attribute("href")
            check("a declaration offers Report a problem, filled in", "template=problem.yml" in report and "declaration=" in report and "version=" in report)
            if shots:
                flagged.screenshot(path=str(shots / "site-problem.png"))
            check("no errors in the page", not errors)
            browser.close()
    except AssertionError as failure:
        print("FAIL:", failure, "| page errors:", errors)
        return 1
    finally:
        server.shutdown()
    print(f"PASS: {len(passed)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
