"""Context builders: full repo, touched files, and a skeleton ladder (L0-L3) built with Python's ast."""
import ast
from pathlib import Path

SKIP = {".git", "docs", "__pycache__", ".github", "build", "dist"}

def py_files(root: Path):
    return sorted(p for p in root.rglob("*.py") if not (set(p.relative_to(root).parts) & SKIP))

def full_repo(root: Path, files=None):
    out = []
    for p in (files or py_files(root)):
        rel = p.relative_to(root) if p.is_absolute() else p
        text = (root / rel).read_text()
        out.append(f"### FILE: {rel}\n```python\n{text}\n```")
    return "\n\n".join(out)

def _module_name(rel: Path):
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)

def _imports(tree, rel):
    mods = []
    pkg = _module_name(rel).split(".")[:-1] if rel.name != "__init__.py" else _module_name(rel).split(".")
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods += [(a.name, None) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                up = pkg[: len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                base = ".".join(up + ([base] if base else []))
            mods.append((base, [a.name for a in n.names]))
    return mods

def _sig(n, src):
    seg = ast.get_source_segment(src, n) or ""
    head = []
    for line in seg.splitlines():
        head.append(line)
        if line.rstrip().endswith(":"):
            break
    return " ".join(h.strip() for h in head)

def _defs(tree, src, docs, indent=""):
    lines = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in getattr(n, "decorator_list", []):
                lines.append(f"{indent}@{ast.get_source_segment(src, d)}")
            lines.append(f"{indent}{_sig(n, src)}  # L{n.lineno}")
            if docs and ast.get_docstring(n):
                first = ast.get_docstring(n).strip().splitlines()[0]
                lines.append(f'{indent}    """{first}"""')
            if isinstance(n, ast.ClassDef):
                lines += _defs(n, src, docs, indent + "    ")
        elif isinstance(n, (ast.Assign, ast.AnnAssign)) and not indent:
            seg = (ast.get_source_segment(src, n) or "").splitlines()[0]
            lines.append(seg[:120])
    return lines

def skeleton(root: Path, level: int):
    """L0 file tree; L1 + imports and imported-by graph; L2 + signatures; L3 + docstring first lines."""
    files = py_files(root)
    rels = [p.relative_to(root) for p in files]
    if level == 0:
        return "### REPO FILE TREE\n" + "\n".join(str(r) for r in rels)
    modmap = {_module_name(r): r for r in rels}
    info, imported_by = {}, {r: set() for r in rels}
    for p, r in zip(files, rels):
        src = p.read_text()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            info[r] = (src, None, []); continue
        imps = _imports(tree, r)
        info[r] = (src, tree, imps)
        for mod, names in imps:
            for cand in [mod] + [f"{mod}.{n}" for n in (names or [])]:
                if cand in modmap and modmap[cand] != r:
                    imported_by[modmap[cand]].add(r)
    out = ["### REPO SKELETON (level %d)" % level]
    for r in rels:
        src, tree, imps = info[r]
        out.append(f"\n## {r}")
        local = sorted({f"{m}" + (f" ({', '.join(n)})" if n else "") for m, n in imps})
        if local:
            out.append("imports: " + "; ".join(local))
        if imported_by[r]:
            out.append("imported by: " + ", ".join(sorted(map(str, imported_by[r]))))
        if level >= 2 and tree is not None:
            out += _defs(tree, src, docs=level >= 3)
    return "\n".join(out)
