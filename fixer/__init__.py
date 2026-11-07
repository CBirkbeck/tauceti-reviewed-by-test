"""The review fixer: twice a day, in the answerer's run (one system since 2026-11-07: `answerer/systemd`, every
twelve hours, after the answering), Claude Opus 5.5 takes each no and suggestion that a person (not an AI agent) left
on the review site since the fixer started, decides whether Tau Ceti should change, and if so makes the change in
its own checkout, where it can only read and edit Tau Ceti's files and build them sealed off. The run, not the
model, then checks the change, opens the pull request and replies on the review's issue naming it (`/addressed`,
scripts/pr_links.py); and in each run it first sees its pull requests through Tau Ceti's review (`follow.py`):
merge conflicts, CI failures, the AI reviewers' findings and people's comments. A declaration of Mathlib is never
changed: the reply says what a person should propose upstream. The design is
docs/superpowers/specs/2026-11-07-review-fixer-design.md."""
