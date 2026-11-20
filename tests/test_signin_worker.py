import json
import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path
from urllib.parse import urlsplit

SIGNIN = Path(__file__).resolve().parents[1] / "signin"
SETTINGS = Path(__file__).resolve().parents[1] / "data" / "settings.json"


class SigninWorkerTests(unittest.TestCase):
    """The sign-in helper's own tests (signin/worker.test.mjs), in Node, as Cloudflare runs it."""

    @unittest.skipUnless(shutil.which("node"), "no Node here")
    def test_the_helper(self):
        r = subprocess.run(["node", "--test", "worker.test.mjs"], cwd=SIGNIN, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("# fail 0", r.stdout)

    def test_the_sites_that_may_ask(self):
        """The helper's settings (wrangler.toml, as deployed) let the site's own pages ask, which sign in and come back
        to its address (settings.json's site.url, web/signin.js), and the public address, taucetiproject.org/review/,
        which reads the same data; and the site's Pages before the move, for a sign-in begun there."""
        allowed = tomllib.loads((SIGNIN / "wrangler.toml").read_text(encoding="utf-8"))["vars"]["ALLOWED_ORIGINS"]
        origins = [o.strip() for o in allowed.split(",")]
        site = urlsplit(json.loads(SETTINGS.read_text(encoding="utf-8"))["site"]["url"])
        self.assertIn(f"{site.scheme}://{site.netloc}", origins)
        for origin in ("https://cbirkbeck.github.io", "https://taucetiproject.org"):
            self.assertIn(origin, origins)


if __name__ == "__main__":
    unittest.main()
