import shutil
import subprocess
import unittest
from pathlib import Path

SIGNIN = Path(__file__).resolve().parents[1] / "signin"


class SigninWorkerTests(unittest.TestCase):
    """The sign-in helper's own tests (signin/worker.test.mjs), in Node, as Cloudflare runs it."""

    @unittest.skipUnless(shutil.which("node"), "no Node here")
    def test_the_helper(self):
        r = subprocess.run(["node", "--test", "worker.test.mjs"], cwd=SIGNIN, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("# fail 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
