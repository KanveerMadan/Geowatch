"""
Minimal SFINCS I/O and runner for the flood-core prototype (synthetic cases).

Writes a regular-grid SFINCS model with ASCII inputs (inputformat = asc),
runs the pinned Docker image, samples the container's memory while it runs,
and reads the NetCDF map output with h5py. No hydromt: every input written
is visible here.

Pinned image: deltares/sfincs-cpu:sfincs-v2.4.1 (sha256:cab764e13a6c...),
linux/amd64. On an arm64 host it runs under emulation, so wall-clock times
are an upper bound for native execution.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid

import numpy as np

IMAGE = "deltares/sfincs-cpu:sfincs-v2.4.1"
TREF = "20000101 000000"


def write_grid(path: str, a: np.ndarray, fmt: str) -> None:
    """Rows written n = 1 (y0, south) first."""
    np.savetxt(path, np.asarray(a), fmt=fmt)


def write_model(d: str, z: np.ndarray, msk: np.ndarray, dx: float, tstop_s: float,
                dtout_s: float, manning: float = 0.04, rain=None, bnd=None, bzs=None,
                src=None, dis=None, zsini: float | None = None, extra: dict | None = None) -> None:
    """z, msk: (nmax, mmax) arrays, row 0 = y0. rain: [(t_s, mm/h)].
    bnd: [(x, y)], bzs: [(t_s, zs...)]; src: [(x, y)], dis: [(t_s, q...)]."""
    os.makedirs(d, exist_ok=True)
    nmax, mmax = z.shape
    write_grid(os.path.join(d, "sfincs.dep"), z, "%.4f")
    write_grid(os.path.join(d, "sfincs.msk"), msk.astype(int), "%d")
    inp = {"mmax": mmax, "nmax": nmax, "dx": dx, "dy": dx, "x0": 0.0, "y0": 0.0, "rotation": 0.0,
           "tref": TREF, "tstart": TREF, "tstop": _t(tstop_s), "dtout": dtout_s, "dtmaxout": tstop_s,
           "dthisout": dtout_s, "alpha": 0.5, "manning": manning, "inputformat": "asc",
           "outputformat": "net", "depfile": "sfincs.dep", "mskfile": "sfincs.msk"}
    if zsini is not None:
        inp["zsini"] = zsini
    if rain is not None:
        np.savetxt(os.path.join(d, "sfincs.prcp"), np.asarray(rain, dtype=float), fmt="%.4f")
        inp["precipfile"] = "sfincs.prcp"
    if bnd is not None:
        np.savetxt(os.path.join(d, "sfincs.bnd"), np.asarray(bnd, dtype=float), fmt="%.3f")
        np.savetxt(os.path.join(d, "sfincs.bzs"), np.asarray(bzs, dtype=float), fmt="%.4f")
        inp["bndfile"], inp["bzsfile"] = "sfincs.bnd", "sfincs.bzs"
    if src is not None:
        np.savetxt(os.path.join(d, "sfincs.src"), np.asarray(src, dtype=float), fmt="%.3f")
        np.savetxt(os.path.join(d, "sfincs.dis"), np.asarray(dis, dtype=float), fmt="%.4f")
        inp["srcfile"], inp["disfile"] = "sfincs.src", "sfincs.dis"
    inp.update(extra or {})
    with open(os.path.join(d, "sfincs.inp"), "w") as f:
        for k, v in inp.items():
            f.write(f"{k:<14}= {v}\n")


def _t(seconds: float) -> str:
    s = int(round(seconds))
    return f"20000101 {s // 3600:02d}{(s % 3600) // 60:02d}{s % 60:02d}" if s < 86400 else \
        f"200001{1 + s // 86400:02d} {(s % 86400) // 3600:02d}{(s % 3600) // 60:02d}{s % 60:02d}"


def _mem_mib(txt: str) -> float | None:
    m = re.match(r"\s*([\d.]+)\s*([KMG]i?B)", txt)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)
    return v * {"KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}[u]


def run(d: str, poll_s: float = 0.25) -> dict:
    """Run SFINCS in d; return wall time, peak container memory (MiB) and
    the solver's own reported runtime, plus the log tail."""
    name = f"sfincs-{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    # Peak resident memory of the sfincs process itself (VmHWM, monotonic),
    # polled inside the container; docker stats misses short runs.
    probe = ("sfincs & p=$!; hwm=0; while kill -0 $p 2>/dev/null; do "
             "v=$(awk '/VmHWM/{print $2}' /proc/$p/status 2>/dev/null); "
             "[ -n \"$v\" ] && [ \"$v\" -gt \"$hwm\" ] && hwm=$v; sleep 0.05; done; "
             "wait $p; rc=$?; echo \"VMHWM_KB=$hwm\"; exit $rc")
    # Memory cap per container (8 GB Mac; one SFINCS job at a time). Does not
    # change results; a run that needs more is killed, not swapped.
    mem = os.environ.get("SFINCS_DOCKER_MEMORY", "3g")
    subprocess.run(["docker", "run", "-d", "--name", name, "--platform", "linux/amd64",
                    "--memory", mem, "--memory-swap", mem,
                    "-v", f"{os.path.abspath(d)}:/data", "--entrypoint", "sh", IMAGE, "-c", probe],
                   check=True, capture_output=True)
    peak = 0.0
    while True:
        st = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name],
                            capture_output=True, text=True).stdout.strip()
        if st != "true":
            break
        s = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name],
                           capture_output=True, text=True).stdout
        m = _mem_mib(s)
        if m:
            peak = max(peak, m)
        time.sleep(poll_s)
    wall = time.time() - t0
    log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
    code = subprocess.run(["docker", "inspect", "-f", "{{.State.ExitCode}}", name],
                          capture_output=True, text=True).stdout.strip()
    subprocess.run(["docker", "rm", name], capture_output=True)
    text = log.stdout + log.stderr
    with open(os.path.join(d, "sfincs_log.txt"), "w") as f:
        f.write(text)
    hwm = re.findall(r"VMHWM_KB=(\d+)", text)
    sfincs_peak = int(hwm[-1]) / 1024 if hwm else None
    solver = re.findall(r"Total time\s*:?\s*([\d.]+)", text) or re.findall(r"[Tt]otal.*?([\d.]+)\s*s", text)
    return {"wall_s": round(wall, 2), "container_peak_mem_mib_sampled": round(peak, 1),
            "sfincs_peak_rss_mib": None if sfincs_peak is None else round(sfincs_peak, 1), "exit_code": code,
            "solver_reported_s": float(solver[-1]) if solver else None, "log_tail": text[-1500:]}


def read_map(d: str) -> dict:
    import h5py
    with h5py.File(os.path.join(d, "sfincs_map.nc"), "r") as f:
        out = {k: f[k][()] for k in f.keys() if hasattr(f[k], "shape")}
    return out


def save_json(path: str, obj) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
