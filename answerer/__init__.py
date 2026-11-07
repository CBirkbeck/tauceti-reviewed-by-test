"""The review answerer: every twelve hours, Claude answers the open noes and questions about the library on
the review site, mathematics only, and proposes docstring fixes to the library where one is wrong; then, in the
same run, the fixer (`fixer/`) sees its pull requests through review and settles people's new reviews in pull
requests (one system since 2026-11-07, `answerer/systemd`).
The design is docs/superpowers/specs/2026-10-25-review-answerer-design.md."""
