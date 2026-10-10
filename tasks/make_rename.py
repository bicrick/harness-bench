"""Helper: generate a whole-word rename task (yaml + reference diff) from a pinned repo checkout."""
import subprocess, sys, re, yaml
from pathlib import Path
repo, tid, kind, old, new, where = sys.argv[1:7]
B = Path(f"/workspace/context-shaping/work/base/{repo}")
T = Path(f"/workspace/context-shaping/tasks/{repo}")
files = subprocess.run(["rg", "-lw", old, "src", "tests", "tinydb"], cwd=B, capture_output=True, text=True).stdout.split()
for f in files:
    p = B / f; p.write_text(re.sub(rf"\b{re.escape(old)}\b", new, p.read_text()))
diff = subprocess.run(["git", "diff"], cwd=B, capture_output=True, text=True).stdout
subprocess.run(["git", "checkout", "-q", "."], cwd=B)
(T / f"{tid}.diff").write_text(diff)
inst = (f"Rename `{old}` ({where}) to `{new}`. Update every reference across the codebase "
        f"(definition, imports, call sites, __all__, docstrings/comments, tests). Do not keep a backwards-compatible alias or the old name.")
d = dict(id=f"{repo}-{tid}", kind=kind, reference=f"{tid}.diff", instruction=inst, touched=sorted(files),
         absent=[rf"\b{old}\b"])
(T / f"{tid}.yaml").write_text(yaml.safe_dump(d, sort_keys=False, width=1000))
print(tid, len(files), "files")
