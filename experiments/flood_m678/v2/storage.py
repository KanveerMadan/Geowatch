"""
M6–M8 v2 storage separation (BUILD_PLAN step 0).

DEV and reserve live in different roots. The reserve root is created mode 000, so an ordinary
process can neither list nor read it. Only score_once (step 6) may open it, after claiming a
durable run id and verifying the published seal, freeze and power receipts.
"""
from __future__ import annotations

import os
import stat

ROOT = os.path.expanduser(os.environ.get("GEOWATCH_M678V2_ROOT", "~/.cache/geowatch/m678v2"))
DEV = os.path.join(ROOT, "dev")
RESERVE = os.path.join(ROOT, "reserve")


class ReserveAccess(PermissionError):
    pass


def init():
    os.makedirs(DEV, exist_ok=True)
    if not os.path.exists(RESERVE):
        os.makedirs(RESERVE)
    os.chmod(RESERVE, 0)           # sealed: no list, no read, no write


def dev_path(*parts) -> str:
    """A path under DEV. Refuses anything that resolves into the reserve root."""
    p = os.path.realpath(os.path.join(DEV, *parts))
    if p == os.path.realpath(RESERVE) or p.startswith(os.path.realpath(RESERVE) + os.sep):
        raise ReserveAccess(f"DEV code may not touch the reserve: {p}")
    if not p.startswith(os.path.realpath(DEV) + os.sep) and p != os.path.realpath(DEV):
        raise ReserveAccess(f"path escapes the DEV root: {p}")
    return p


def reserve_is_sealed() -> bool:
    return os.path.isdir(RESERVE) and stat.S_IMODE(os.stat(RESERVE).st_mode) == 0


def open_reserve(receipt_ok: bool, run_id: str) -> str:
    """Step 6 only. Unseals the reserve root for one verified run."""
    if not receipt_ok or not run_id:
        raise ReserveAccess("the reserve opens only for a verified score_once run")
    os.chmod(RESERVE, 0o700)
    return RESERVE
