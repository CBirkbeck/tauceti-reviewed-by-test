"""What the answerer posts, cleaned first.

The model writes its reply after reading a report that anyone can file, so the reply is treated as
untrusted text: whatever it says, posting it must not attribute it to anyone else, run a command,
ping someone, show an image, or link anywhere but where a mathematical reader would look.

- HTML comments go: an agent mark or a Reviewed-by mark in them would take over the comment's
  attribution in intake, which reads the first it finds.
- Tags are shown, not rendered (`<` opening a tag becomes `&lt;`), and numeric character
  references go (`&#64;` renders as `@`).
- Links stay only to the hosts in `HOSTS`; any other becomes its text, a bare address its host.
  Images become their alt text.
- `@` mentions and `#123` references are defused with a zero-width space.
- A line starting with a `/command` is defused too: intake reads a command on a comment's first line.
- Code spans and blocks are left as they are, apart from the comments and commands.
- At most `limit` characters, cut at a paragraph.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

ZWSP = "​"

#: (host, path prefixes or None for any path) a reply may link to.
HOSTS = {
    "github.com": ("/TauCetiProject/", "/leanprover-community/", "/CBirkbeck/tauceti-reviewed-by-test"),
    "cbirkbeck.github.io": ("/tauceti-reviewed-by-test",),
    "taucetiproject.org": None,
    "leanprover-community.github.io": None,
    "arxiv.org": None,
    "doi.org": None,
    "dx.doi.org": None,
    "zbmath.org": None,
    "mathscinet.ams.org": None,
    "www.ams.org": None,
    "www.numdam.org": None,
    "numdam.org": None,
    "stacks.math.columbia.edu": None,
    "ncatlab.org": None,
    "en.wikipedia.org": None,
    "mathoverflow.net": None,
    "math.stackexchange.com": None,
    "ems.press": None,
    "projecteuclid.org": None,
    "link.springer.com": None,
}

HTML_COMMENT = re.compile(r"<!--.*?(-->|$)", re.S)
CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
URL = re.compile(r"https?://[^\s<>()\[\]`\"']+")
CHARREF = re.compile(r"&#(\d+|[xX][0-9A-Fa-f]+);")
TAG = re.compile(r"<(?=[!?]|/?[A-Za-z][A-Za-z0-9-]*(?:\s|/?>))")
MENTION = re.compile(r"(?<![\w])@(?=[A-Za-z0-9])")
REFERENCE = re.compile(r"#(?=\d)")
COMMAND = re.compile(r"^(\s*)/(?=[A-Za-z])", re.M)
SLOT = "\x00{}\x00"


def allowed(url: str) -> bool:
    try:
        u = urlsplit(url)
    except ValueError:
        return False
    if u.scheme != "https" or u.username or u.password or u.port:
        return False
    host = (u.hostname or "").lower()
    if host not in HOSTS:
        return False
    prefixes = HOSTS[host]
    return prefixes is None or any(u.path.startswith(p) for p in prefixes)


def defuse(text: str) -> str:
    """Mentions, references and tags in running text."""
    text = CHARREF.sub("", text)
    text = TAG.sub("&lt;", text)
    text = MENTION.sub("@" + ZWSP, text)
    return REFERENCE.sub("#" + ZWSP, text)


def clean_prose(text: str) -> str:
    kept: list[str] = []

    def keep(s: str) -> str:
        kept.append(s)
        return SLOT.format(len(kept) - 1)

    text = IMAGE.sub(lambda m: m.group(1), text)
    text = LINK.sub(lambda m: keep(f"[{defuse(m.group(1))}]({m.group(2)})") if allowed(m.group(2)) else m.group(1), text)
    text = URL.sub(lambda m: keep(m.group(0)) if allowed(m.group(0)) else (urlsplit(m.group(0)).hostname or ""), text)
    text = defuse(text)
    return re.sub("\x00(\\d+)\x00", lambda m: kept[int(m.group(1))], text)


def cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n\n", 0, limit - 3)
    return text[:cut if cut > 0 else limit - 3].rstrip() + "\n\n…"


def clean(text: str, limit: int = 8000) -> str:
    text = HTML_COMMENT.sub("", text or "").replace("\x00", "")
    parts = CODE.split(text)
    # CODE has one group: the split alternates prose, code, prose, …
    text = "".join(p if i % 2 else clean_prose(p) for i, p in enumerate(parts))
    text = COMMAND.sub(lambda m: m.group(1) + ZWSP + "/", text)
    return cap(text.strip(), limit)
