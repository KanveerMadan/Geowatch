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

**Never branch off `unmixing-ceiling-investigation`**, and never branch off
another work-stream branch. Investigation branches carry decisions that have
**not** been signed off by a human. Building on top of one silently inherits
its unsigned premises, and if a decision is later reversed, everything
downstream has to be unpicked.

`unmixing-ceiling-investigation` is the standing example: as of this writing it
is 12 commits ahead of `master` and carries four decisions marked `⚠️` awaiting
sign-off — item 21, and Decisions 11, 13 and 14. It does **not** get merged
into `master` until those are signed off. It stays deliberately separate. That
is not neglect; it is the point.

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

## Before making this repository public

This repo is **private**, and some of its contents assume that. Do not flip it
public without clearing these first:

- **C34 is an unfixed path-traversal finding at a read boundary**
  (`api.py:314`, `GET /api/runs/{run_id}`), scheduled as build-manual item 47.
  `04_FINDINGS_LEDGER.md` documents the sink, the file, the line, the bug
  class, and explicitly notes which attack variants were *not* tried. That is
  a working exploit guide for a live bug. Fix item 47 first.
- **The API has no authentication of any kind** — see the C40 proposal under
  discussion. `POST /api/scheduler/trigger` is docstringed "(admin use)" and is
  reachable by anyone who can reach the port.
- **A personal email address is hardcoded** as the HTTP User-Agent in
  `ingestion/exposure_sources.py:308` and `ingestion/osm_dem.py:55`. This is
  *required* by the Nominatim and Overpass usage policies, so it is correct as
  written and should be left alone while the repo is private — but it is a
  public email the moment the repo is public.
- **A revoked ngrok authtoken remains in history**, in the root commit
  `2ac07d5`, inside `notebooks/archive/Untitled10.ipynb`. The token is revoked
  and therefore inert, and history was deliberately not rewritten — rewriting
  all 24 commits would change `ecfe370`, which anchors this branch discipline.
  It is harmless, but expect secret scanners to flag it.

There is deliberately **no LICENSE file**. Adding one is a decision about
publication that has not been made.
