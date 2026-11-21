"""tools/secrets_scan.py must BLOCK (exit 1) on secrets and private details,
and pass clean diffs. Test strings are assembled at run time, so this file
does not trip the scan itself."""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(os.path.dirname(HERE), "tools", "secrets_scan.py")
HOME = "/" + "Users" + "/alice/"          # an absolute home path
ENV_VALUE = "proj-" + "secret-123456"


def _repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    run = lambda *a: subprocess.run(a, cwd=r, check=True, capture_output=True)   # noqa: E731
    run("git", "init", "-q")
    run("git", "config", "user.email", "someone" + "@example.org")
    run("git", "config", "user.name", "t")
    (r / ".gitignore").write_text(".env\n")
    (r / ".env").write_text(f"GEE_PROJECT_ID={ENV_VALUE}\n")
    (r / "a.txt").write_text("start\n")
    run("git", "add", "a.txt", ".gitignore")
    run("git", "commit", "-qm", "init")
    return r, run


def _scan(r, *args):
    return subprocess.run([sys.executable, SCAN, "--repo", str(r), *args],
                          capture_output=True, text=True)


def _stage(r, run, name, text):
    (r / name).write_text(text)
    run("git", "add", "-f", name)


def test_clean_diff_passes(tmp_path):
    r, run = _repo(tmp_path)
    _stage(r, run, "b.py", "x = 1\npath = '~/.cache/geowatch'\n")
    p = _scan(r, "--staged")
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("text,rule", [
    (f"data = '{HOME}geowatch/data'\n", "home_path"),
    (f"project = '{ENV_VALUE}'\n", "env_value"),
    ("mail = 'someone" + "@example.org'\n", "user_email"),
    ("-----BEGIN " + "RSA PRIVATE KEY-----\n", "private_key"),
    ("tok = 'ghp_" + "a" * 36 + "'\n", "github_token"),
])
def test_secret_lines_block_with_exit_1(tmp_path, text, rule):
    r, run = _repo(tmp_path)
    _stage(r, run, "b.py", text)
    p = _scan(r, "--staged")
    assert p.returncode == 1
    assert rule in p.stderr and "BLOCKED" in p.stderr
    assert ENV_VALUE not in p.stderr and HOME not in p.stderr       # masked


def test_staged_env_file_blocks(tmp_path):
    r, run = _repo(tmp_path)
    run("git", "add", "-f", ".env")
    p = _scan(r, "--staged")
    assert p.returncode == 1 and "secret_file" in p.stderr


def test_allow_marker_and_generic_home_pass(tmp_path):
    r, run = _repo(tmp_path)
    _stage(r, run, "b.py", f"x = '{HOME}'  # secrets-scan: allow\n"
                           "y = '/" + "home/runner/work'\n")
    assert _scan(r, "--staged").returncode == 0


def test_range_mode_scans_commits(tmp_path):
    r, run = _repo(tmp_path)
    _stage(r, run, "b.py", f"x = '{HOME}a'\n")
    run("git", "commit", "-qm", "leak")
    assert _scan(r, "--range", "HEAD~1..HEAD").returncode == 1
    _stage(r, run, "c.py", "ok = 1\n")
    run("git", "commit", "-qm", "fine")
    assert _scan(r, "--range", "HEAD~1..HEAD").returncode == 0


def test_only_added_lines_count(tmp_path):
    r, run = _repo(tmp_path)
    _stage(r, run, "b.py", f"x = '{HOME}a'  # secrets-scan: allow\n")
    run("git", "commit", "-qm", "legacy")
    (r / "b.py").write_text("x = 'fixed'\n")
    run("git", "add", "b.py")
    assert _scan(r, "--staged").returncode == 0
