#!/usr/bin/env python3
"""
Blocking secrets scan for commits and pushes. Exits 1 when an added line
holds a secret or a private detail, and 0 otherwise. Use it as a gate:

    python tools/secrets_scan.py --staged && git commit ...
    python tools/secrets_scan.py --range origin/<branch>..HEAD && git push ...
    tools/safe_push.sh [remote] [branch]                 # scan, then push

It checks only ADDED lines in the diff ("going forward"). What it blocks:
- absolute home-directory paths (/Users/<name>/, /home/<name>/, C:\\Users\\<name>\\);
- any value of a key in the repo's .env (read locally, never printed);
- the git user's e-mail address;
- private-key headers;
- common token shapes (GitHub, AWS, Google API keys, Slack, OpenAI/Anthropic-style sk- keys);
- staged .env, *.pem or credentials files.

A line carrying the marker `secrets-scan: allow` is skipped. Use it only
for a documented false positive, e.g. a pattern inside this scanner's own
tests.

Matches are reported by file, line and rule; the matched text is masked.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ALLOW = "secrets-scan: allow"
RULES = [
    ("home_path", re.compile(r"(?<![\w.])(/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\)")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("sk_key", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{24,}\b")),
]
GENERIC_HOMES = {"runner", "user", "username", "you", "me", "name", "example", "<name>"}
BAD_FILES = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|credentials(\.json)?|.*\.p12|id_rsa.*|\.netrc|\.cdsapirc|gfm\.json|ems\.json)$")
GFM_CREDS = os.path.expanduser("~/.config/geowatch/gfm.json")      # GFM login (R30); values blocked, never printed
EMS_CREDS = os.path.expanduser("~/.config/geowatch/ems.json")      # EMS session cookie (R39); values blocked, never printed


def git(*a, cwd=None) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def repo_root(cwd=None) -> str:
    return git("rev-parse", "--show-toplevel", cwd=cwd).strip()


def env_values(root: str) -> list:
    """Values of the .env next to the repo root (or its main worktree), >= 6 chars."""
    vals = []
    paths = [os.path.join(root, ".env")]
    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root).strip()
        paths.append(os.path.join(os.path.dirname(common), ".env"))
    except subprocess.CalledProcessError:
        pass
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in open(p, errors="ignore"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            v = line.split("=", 1)[1].strip().strip("'\"")
            if len(v) >= 6 and v.lower() not in ("true", "false"):
                vals.append(v)
    for cred in (GFM_CREDS, EMS_CREDS):
        if not os.path.exists(cred):
            continue
        try:
            import json
            for v in json.load(open(cred)).values():
                if isinstance(v, str) and len(v) >= 6:
                    vals.append(v)
        except Exception:          # noqa: BLE001  (unreadable file: the file-name rule still applies)
            pass
    return vals


def user_email(root: str) -> str | None:
    try:
        e = git("config", "user.email", cwd=root).strip()
        return e or None
    except subprocess.CalledProcessError:
        return None


def added_lines(diff: str):
    """(file, line number, text) for every added line of a unified diff."""
    f, n = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            f = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            n = int(m.group(1)) if m else 0
        elif line.startswith("+") and f:
            yield f, n, line[1:]
            n += 1
        elif not line.startswith("-"):
            n += 1


def changed_files(diff: str) -> list:
    return [l[6:] for l in diff.splitlines() if l.startswith("+++ b/")]


def scan(diff: str, secrets: list, email: str | None) -> list:
    hits = []
    for f in changed_files(diff):
        if BAD_FILES.search(f):
            hits.append((f, 0, "secret_file", f))
    for f, n, text in added_lines(diff):
        if ALLOW in text:
            continue
        for rule, rx in RULES:
            for m in rx.finditer(text):
                tok = m.group(0)
                if rule == "home_path":
                    name = re.split(r"[/\\]", tok.strip("/\\"))[1 if tok[1] != ":" else 2].lower()
                    if name in GENERIC_HOMES:
                        continue
                hits.append((f, n, rule, tok))
        for v in secrets:
            if v in text:
                hits.append((f, n, "env_value", v))
        if email and email.lower() in text.lower():
            hits.append((f, n, "user_email", email))
    return hits


def mask(s: str) -> str:
    return s[:3] + "…" if len(s) > 4 else "…"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true", help="scan the staged diff")
    g.add_argument("--range", help="scan a revision range, e.g. origin/main..HEAD")
    g.add_argument("--diff-file", help="scan a unified diff from a file (tests)")
    ap.add_argument("--repo", default=None)
    a = ap.parse_args(argv)
    root = repo_root(a.repo)
    if a.diff_file:
        diff = open(a.diff_file).read()
    elif a.staged:
        diff = git("diff", "--cached", "-U0", "--no-color", cwd=root)
    else:
        diff = git("diff", "-U0", "--no-color", a.range, cwd=root)
    hits = scan(diff, env_values(root), user_email(root))
    if hits:
        print(f"secrets scan: BLOCKED, {len(hits)} finding(s)", file=sys.stderr)
        for f, n, rule, tok in hits[:50]:
            print(f"  {f}:{n}: {rule} ({mask(tok)})", file=sys.stderr)
        return 1
    print("secrets scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
