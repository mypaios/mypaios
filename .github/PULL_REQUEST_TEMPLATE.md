<!--
Thanks for contributing to MyPaiOS! Please keep PRs small and focused —
one bug fix or feature per PR. See CONTRIBUTING.md for the full guidelines.
-->

## What this changes

<!-- Short explanation of the bug fixed or feature added, and why. -->

Fixes #

## How it was tested

<!--
What you ran, and what you saw. "The test suite passes" alone is not enough
for behavior changes — describe a manual check in the running app too.
-->

- [ ] `python -m pytest` (or the smallest relevant subset — name it)
- [ ] Manually verified in the running app
- [ ] For UI changes: screenshot / short clip attached (mobile too, if affected)

## Checklist

- [ ] **DCO:** every commit is signed off (`git commit -s`, adding `Signed-off-by: Name <email>`). Unsigned commits can be fixed with `git rebase --signoff`.
- [ ] PR targets `main`.
- [ ] One focused change; no unrelated cleanup, formatting, or refactors mixed in.
- [ ] No secrets, API keys, personal paths, or private logs in the diff or description.
- [ ] Visual changes reuse existing CSS variables/components, no Unicode emoji in UI or code (see CONTRIBUTING.md "Style and visual changes").
- [ ] No internal identifiers renamed (`paios-*` keys, `PAIOS_*` env vars, `X-PAIOS-*` headers — see AGENTS.md).
- [ ] No code ported from upstream Odysseus commits after 2026-06-09 (AGPL — incompatible with this MIT fork).
