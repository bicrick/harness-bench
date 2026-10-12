"""Grader: tests pass + no leftover references (missed callers) + task-specific check."""
import re, subprocess, sys
from pathlib import Path
from .context import py_files

def _env(root, task):
    pp = task.get("repo", {}).get("pythonpath", ".")
    return {"PYTHONPATH": str(root / pp), "PATH": "/usr/bin:/bin"}

def run_tests(root: Path, task, timeout=300):
    args = task.get("repo", {}).get("pytest_args", ["-c", "/dev/null"])
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", *args, "-p", "no:cacheprovider", "tests"],
                       cwd=root, capture_output=True, text=True, timeout=timeout, env=_env(root, task))
    tail = (r.stdout + r.stderr).strip().splitlines()[-15:]
    return r.returncode == 0, "\n".join(tail)

def missed_refs(root: Path, patterns):
    hits = []
    for p in py_files(root):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            for pat in patterns:
                if re.search(pat, line):
                    hits.append(f"{p.relative_to(root)}:{i}: {line.strip()[:100]}")
    return hits

def check_cmd(root: Path, cmd, task):
    if not cmd:
        return True, ""
    r = subprocess.run([sys.executable, "-c", cmd], cwd=root, capture_output=True, text=True, timeout=60,
                       env=_env(root, task))
    return r.returncode == 0, (r.stderr or "")[-500:]

def diffstat(root: Path):
    r = subprocess.run(["git", "diff", "--numstat"], cwd=root, capture_output=True, text=True)
    add = rem = files = 0
    for line in r.stdout.splitlines():
        a, d, _ = line.split("\t", 2)
        files += 1; add += int(a) if a.isdigit() else 0; rem += int(d) if d.isdigit() else 0
    new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root, capture_output=True, text=True).stdout.split()
    for f in new:
        files += 1; add += len((root / f).read_text().splitlines())
    return dict(files=files, added=add, removed=rem)

def _comment_only(hit, patterns):
    line = hit.split(": ", 1)[1] if ": " in hit else hit
    code = line.split("#", 1)[0]
    return not any(re.search(p, code) for p in patterns) or line.lstrip().startswith((":", "`", "This", "Load"))

def grade(root: Path, task):
    tests_ok, test_tail = run_tests(root, task)
    missed = missed_refs(root, task.get("absent", []))
    chk_ok, chk_err = check_cmd(root, task.get("check"), task)
    code_missed = [m for m in missed if not _comment_only(m, task.get("absent", []))]
    return dict(passed=bool(tests_ok and not missed and chk_ok), tests_ok=tests_ok, missed_callers=len(missed),
                missed_code_refs=len(code_missed),
                missed=missed[:20], check_ok=chk_ok, check_err=chk_err, test_tail=test_tail, diff=diffstat(root))
