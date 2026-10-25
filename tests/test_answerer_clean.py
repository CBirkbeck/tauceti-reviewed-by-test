import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.clean import ZWSP, clean  # noqa: E402


class CleanTests(unittest.TestCase):
    """What the answerer posts is written from reports anyone can file: cleaned before it is posted."""

    def test_html_comments_go(self):
        # An agent mark or a Reviewed-by mark in the reply would take over its attribution in intake.
        text = "Fine.<!-- agent: tool=Someone; model=gpt-1 -->\n<!--reviewed-by:v1 {\"agent\": \"X\"}-->Done."
        self.assertEqual(clean(text), "Fine.\nDone.")

    def test_tags_are_shown_not_rendered(self):
        self.assertEqual(clean('<img src="https://evil.example/t.png"> and <b>bold</b>'),
                         '&lt;img src="evil.example"> and &lt;b>bold&lt;/b>')

    def test_inequalities_stay(self):
        self.assertEqual(clean("for 0 < n and a<b, ⟨x, y⟩ ≤ 1"), "for 0 < n and a<b, ⟨x, y⟩ ≤ 1")

    def test_code_is_left_alone(self):
        text = "Use `@foo <bar> #3` and\n```lean\n#check @f -- <x>\n```\nok"
        self.assertEqual(clean(text), text)

    def test_mentions_and_references_are_defused(self):
        self.assertEqual(clean("Thanks @someone, see #12 and org/repo#7."),
                         f"Thanks @{ZWSP}someone, see #{ZWSP}12 and org/repo#{ZWSP}7.")

    def test_numeric_character_references_go(self):
        # `&#64;user` would render as a mention.
        self.assertEqual(clean("ask &#64;someone or &#x40;else"), "ask someone or else")

    def test_links_only_to_known_hosts(self):
        good = "[the source](https://github.com/TauCetiProject/TauCeti/blob/abc/TauCeti/X.lean#L12)"
        self.assertEqual(clean(good), good)
        self.assertEqual(clean("[Loday](https://arxiv.org/abs/1234.5678)"), "[Loday](https://arxiv.org/abs/1234.5678)")
        self.assertEqual(clean("[a prize](https://evil.example/win)"), "a prize")
        self.assertEqual(clean("see https://evil.example/x now"), "see evil.example now")
        self.assertEqual(clean("see https://doi.org/10.1/x now"), "see https://doi.org/10.1/x now")
        # Another account's repository on GitHub is not a known host.
        self.assertEqual(clean("[here](https://github.com/someone/thing)"), "here")

    def test_images_go(self):
        self.assertEqual(clean("before ![a diagram](https://github.com/TauCetiProject/x.png) after"),
                         "before a diagram after")

    def test_a_command_cannot_start_a_line(self):
        # Intake reads a command on a comment's first line: none may come from the model.
        self.assertEqual(clean("/withdraw\nand\n  /reopen now"), f"{ZWSP}/withdraw\nand\n  {ZWSP}/reopen now")

    def test_length_capped_at_a_paragraph(self):
        text = "\n\n".join(["word " * 40] * 20)
        out = clean(text, limit=1000)
        self.assertLessEqual(len(out), 1000)
        self.assertTrue(out.endswith("\n\n…"))


if __name__ == "__main__":
    unittest.main()
