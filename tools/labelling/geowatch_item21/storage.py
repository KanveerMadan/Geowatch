"""Human-initiated timing records and profile-local review decisions."""
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path


def now():
    return datetime.now().astimezone()


def timer(tile, name=None, at=None):
    """Start/stop only when explicitly invoked, preserving other metadata keys."""
    import fcntl
    from contextlib import ExitStack
    path = tile / "metadata.json"
    at = at or now()
    # Lock the directory inode, which survives atomic metadata replacement.
    fd = os.open(tile, os.O_RDONLY)
    with ExitStack() as stack:
        stack.callback(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        if path.is_symlink():
            raise ValueError("The tile metadata must be a local file.")
        original = path.read_bytes()
        meta = json.loads(original)
        owner = (meta.get("labeller") or name or "").strip()
        if not owner:
            raise ValueError("Enter the labeller's name to start timing.")
        timing = meta.setdefault("timing", {})
        sessions = timing.setdefault("item21_sessions", [])
        active = sessions[-1] if sessions and not sessions[-1].get("end_local") else None
        if active:
            start = datetime.fromisoformat(active["start_local"])
            seconds = at.timestamp() - start.timestamp()
            if seconds < 0:
                raise ValueError("The stop time precedes the start time.")
            active.update(end_local=at.isoformat(), seconds=seconds)
            timing["end_local"] = at.isoformat()
            minutes = timing.get("item21_previous_minutes", 0) + sum(s["seconds"] for s in sessions)/60
            timing["minutes"] = round(minutes, 3)
            message = f"Timer stopped. Total recorded time: {minutes:.1f} minutes."
        else:
            if not sessions:
                if timing.get("start_local") and not timing.get("end_local"):
                    raise ValueError("The metadata contains an unfinished earlier timer. Resolve that record first.")
                timing["item21_previous_minutes"] = float(timing.get("minutes") or 0)
            sessions.append({"start_local": at.isoformat(), "labeller": owner})
            timing["start_local"] = timing.get("start_local") or at.isoformat()
            timing["end_local"] = None
            meta["labeller"] = owner
            meta["labelling_date"] = meta.get("labelling_date") or at.date().isoformat()
            message = f"Timer started for {owner}."
        with tempfile.NamedTemporaryFile("w", dir=tile, delete=False, encoding="utf-8") as out:
            tmp = Path(out.name)
            stack.callback(tmp.unlink, missing_ok=True)
            json.dump(meta, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        if path.read_bytes() != original:
            raise ValueError("Metadata changed in another editor. Retry after saving it.")
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
        return message


class Log:
    def __init__(self, path):
        self.path = path

    def write(self, tile, candidate, action, details=""):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS review (tile TEXT, candidate TEXT, action TEXT, recorded TEXT, details TEXT)")
            db.execute("INSERT INTO review VALUES (?, ?, ?, ?, ?)",
                       (str(tile), candidate, action, now().isoformat(), details))

    def rejected(self, tile):
        if not self.path.exists():
            return set()
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT candidate, action FROM review WHERE tile=? "
                              "AND action IN ('reject','reopen') ORDER BY rowid", (str(tile),))
            return {k for k, v in dict(rows).items() if v == "reject"}
