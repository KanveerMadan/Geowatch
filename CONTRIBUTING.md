# Contributing to GeoWatch

Working conventions for this repository. They exist so that **progress is
reconstructible from `git log` alone**, with no dependency on an external task
board, a chat transcript, or anyone's memory of what was in flight.

If you are a new session picking this up cold: read this file, then
`05_BUILD_MANUAL.md` for what to build, then `04_FINDINGS_LEDGER.md` for why.

---

## Branches

**One branch per work stream, branched off `master`.**

`master` is the stable line. Every work stream starts there:

```sh
git checkout master
git pull
git checkout -b <work-stream-name>
```

**Never branch off another work-stream branch.** Investigation branches carry
decisions that have **not** been signed off by a human. Building on top of one
silently inherits its unsigned premises, and if a decision is later reversed,
everything downstream has to be unpicked.

`unmixing-ceiling-investigation` is how this rule worked in practice. It
carried four decisions marked `⚠️` — item 21 and Decisions 11, 13 and 14 — and
stayed deliberately separate from `master` until they were signed off. They
were signed off on 2026-09-23; the branch was then merged into
`architecture-pivot-signoff` (`32d066d`), which was merged into `master` on
2026-09-25 (`738c53b`). Work after that (item 21 Phase A, on
`item-21-phase-a`) branches from `master`.

`master` is the default branch on GitHub for the same reason: someone arriving
at this repo must land on the stable line, not on unsigned work.

## Commits

**One commit per build-manual item, with the item number in the subject line.**

```
Item 44: assert band order at the read boundary
```

Not "fix band order", not "item 44", not several items batched together. The
item number is what makes `git log --oneline` a progress report rather than a
diary.

**Each item's commit also flips that item's status in `05_BUILD_MANUAL.md`**,
in the same commit as the work. Status lives on the item heading: `🔓` open,
`✅` done, `⚠️` awaiting human sign-off. So a commit for item 44 touches both
the code and the manual:

```
Item 44: assert band order at the read boundary

- ingestion/sentinel2.py: explicit band-order assertion before read
- 05_BUILD_MANUAL.md: item 44 🔓 → ✅
```

This is the whole mechanism. The manual is the board, the commit is the status
update, and the two cannot drift apart because they move together. If you flip
a status in a separate commit, you have reintroduced the drift this convention
exists to prevent.

A decision that needs human sign-off gets `⚠️` and **stops there**. Do not mark
it `✅` and do not build on it. Record what the evidence showed and what you
propose; leave the call to a human.

## Working tree

**Clean at every item boundary.** `git status` is empty before you start an
item and empty after you finish it. No stashes carried across items, no
half-finished edits to a second item riding along in the same commit.

If you need scratch files, put them outside the repo, or make sure they are
covered by `.gitignore` — check with `git check-ignore -v <path>` rather than
assuming.

## Pushing

**Push after every item, not at the end of a session.**

```sh
git push
```

Both branches track their remote counterparts, so bare `git push` is correct;
you should not need to name a remote or branch.

The reason is blunt: an interrupted session should cost **one item, not a day**.
Sessions get cut off. Anything unpushed is work that has to be redone from
scratch by someone who no longer remembers the reasoning.

---

## Public repository

**This repository is public** (GitHub visibility checked 2026-09-25). What
that means for the items this section used to list as blockers:

- **C34 — path traversal at `GET /api/runs/{run_id}`: fixed.** Item 47
  validates `run_id` at the read boundary; the finding is CLOSED in
  `04_FINDINGS_LEDGER.md`. The ledger entry still describes the sink in
  detail, as a record of a fixed bug.
- **C40 — no API authentication: fixed by item 70** (API-key authentication
  on every endpoint; `api.py` refuses to start without `GEOWATCH_API_KEY`).
  *Note:* the ledger still files C40 under SURVIVES with its pre-fix
  wording; its fate has not been updated.
- **Personal contact email: moved to an environment variable.** The
  Overpass / Nominatim usage policies require a contact in the User-Agent;
  it is now read from `GEOWATCH_CONTACT_EMAIL` (`ingestion/contact.py`,
  `.env.example`) and calls fail loudly without it. It **remains in git
  history by decision** — history is not rewritten.
- **A revoked ngrok authtoken remains in history**, in the root commit
  `2ac07d5`, inside `notebooks/archive/Untitled10.ipynb`. The token is
  revoked and therefore inert, and history was deliberately not rewritten —
  rewriting all commits would change `ecfe370`, which anchors this branch
  discipline. It is harmless, but expect secret scanners to flag it.

There is deliberately **no LICENSE file**. Adding one is a decision about
publication that has not been made.
