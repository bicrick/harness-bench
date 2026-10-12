"""Aider-style SEARCH/REPLACE edit blocks."""
import re
from pathlib import Path

EDIT_FORMAT = """Return your changes ONLY as edit blocks in exactly this format (one block per change, repeat as needed):

path/to/file.py
<<<<<<< SEARCH
exact existing lines to find (copy them verbatim, include enough lines to be unique)
=======
replacement lines
>>>>>>> REPLACE

To create a new file, use an empty SEARCH section. To delete code, use an empty REPLACE section.
To delete or rename a whole file, add a line `DELETE path/to/file.py` (and create the new file with an empty SEARCH block).
Edit every file that needs to change, including tests. Do not output anything else after the edit blocks."""

BLOCK = re.compile(r"^([^\n`]*?\.py)\s*\n(?:```[a-z]*\n)?<<<<<<< SEARCH\n(.*?)^=======\n(.*?)^>>>>>>> REPLACE", re.S | re.M)

DELETE = re.compile(r"^DELETE\s+`?([^\s`]+\.py)`?\s*$", re.M)

def parse(text):
    return [(m.group(1).strip().strip("`*# "), m.group(2), m.group(3)) for m in BLOCK.finditer(text)]

def apply_deletes(root: Path, text):
    errs = []
    for m in DELETE.finditer(text):
        p = (root / m.group(1)).resolve()
        if root.resolve() in p.parents and p.is_file():
            p.unlink()
        else:
            errs.append(f"{m.group(1)}: cannot delete")
    return errs

def apply(root: Path, blocks):
    errors = []
    for path, search, replace in blocks:
        path = re.sub(r"^(?:FILE:|File:|file:)\s*", "", path.strip()).strip("`*# ")
        if not (root / path).exists() and search.strip():
            cands = [q for q in root.rglob("*.py") if str(q).endswith("/" + path)]
            if len(cands) == 1:
                path = str(cands[0].relative_to(root))
        p = (root / path).resolve()
        if root.resolve() not in p.parents:
            errors.append(f"{path}: outside repo"); continue
        if not search.strip():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text((p.read_text() if p.exists() else "") + replace); continue
        if not p.exists():
            errors.append(f"{path}: file not found"); continue
        text = p.read_text()
        if search in text:
            p.write_text(text.replace(search, replace, 1))
        else:
            # whitespace-tolerant fallback on trailing spaces
            s2 = "\n".join(l.rstrip() for l in search.splitlines())
            t2 = "\n".join(l.rstrip() for l in text.splitlines()) + ("\n" if text.endswith("\n") else "")
            if s2 and s2 in t2:
                p.write_text(t2.replace(s2, "\n".join(l.rstrip() for l in replace.splitlines()), 1))
            else:
                errors.append(f"{path}: SEARCH block not found")
    return errors
