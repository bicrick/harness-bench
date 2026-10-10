"""Arm A context strategies. Each returns dict(text/log, usage...) after editing `root` in place."""
import json, re, subprocess
from pathlib import Path
from . import llm, context, edits, grade

SYSTEM = ("You are an expert Python engineer performing a refactor in an existing repository. "
          "Make the requested change completely: update the definition AND every reference (imports, call sites, "
          "tests, strings that name the symbol, __all__). Keep behavior identical otherwise.")

def _acc(stats, u, usd, dt):
    for k, v in u.items():
        stats["tokens"][k] = stats["tokens"].get(k, 0) + v
    stats["cost_usd"] += usd; stats["api_s"] += dt; stats["calls"] += 1

def _new_stats():
    return dict(tokens={}, cost_usd=0.0, api_s=0.0, calls=0, notes={}, transcript=[])

def _log(stats, request, r):
    """Append the full request messages and the raw response content to the transcript."""
    stats["transcript"].append({"request": request, "response": [b.model_dump(exclude_none=True) for b in r.content],
                                "stop_reason": r.stop_reason})

def _text(r):
    return "".join(b.text for b in r.content if b.type == "text")

def _single_shot(root, task, ctx, stats):
    msg = f"{ctx}\n\n### TASK\n{task['instruction']}\n\n{edits.EDIT_FORMAT}"
    r, u, usd, dt = llm.call(SYSTEM, [{"role": "user", "content": msg}])
    _acc(stats, u, usd, dt); _log(stats, [{"role": "user", "content": msg}], r)
    out = _text(r)
    blocks = edits.parse(out)
    stats["notes"]["edit_blocks"] = len(blocks)
    stats["notes"]["apply_errors"] = edits.apply(root, blocks) + edits.apply_deletes(root, out)
    stats["notes"]["prompt_tokens_est"] = len(msg) // 4
    return stats

def full(root, task):
    return _single_shot(root, task, "### REPOSITORY (all Python files)\n" + context.full_repo(root), _new_stats())

def touched(root, task):
    files = [Path(f) for f in task["touched"] if (root / f).exists()]
    return _single_shot(root, task, "### RELEVANT FILES\n" + context.full_repo(root, files), _new_stats())

def make_skeleton(level):
    def strat(root, task):
        stats = _new_stats()
        sk = context.skeleton(root, level)
        ask = (f"{sk}\n\n### TASK\n{task['instruction']}\n\nYou will be shown the full contents of the files you select. "
               "List EVERY file you need to read or edit (including tests and files that only reference the symbol), "
               "one path per line inside <files></files>. Paths must come from the tree above.")
        r, u, usd, dt = llm.call(SYSTEM, [{"role": "user", "content": ask}])
        _acc(stats, u, usd, dt); _log(stats, [{"role": "user", "content": ask}], r)
        m = re.search(r"<files>(.*?)</files>", _text(r), re.S)
        picked = [l.strip().strip("-* `") for l in (m.group(1) if m else "").splitlines() if l.strip()]
        picked = [p for p in dict.fromkeys(picked) if (root / p).is_file()][:25]
        oracle = set(task["touched"])
        stats["notes"]["selected"] = picked
        stats["notes"]["selection_recall"] = round(len(oracle & set(picked)) / len(oracle), 3)
        ctx = sk + "\n\n### SELECTED FILES\n" + context.full_repo(root, [Path(p) for p in picked])
        return _single_shot(root, task, ctx, stats)
    return strat

# ---------------- agentic ----------------
TOOLS = [
    {"name": "list_files", "description": "List all Python files in the repo.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "grep", "description": "Regex search over Python files. Returns file:line: text (max 80 hits).",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "read_file", "description": "Read a file with line numbers.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "edit", "description": "Replace an exact snippet in a file (first occurrence). Empty `search` creates/appends to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "search": {"type": "string"}, "replace": {"type": "string"}},
                      "required": ["path", "search", "replace"]}},
    {"name": "delete_file", "description": "Delete a file (use with edit to move/rename a module).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "run_tests", "description": "Run the test suite; returns the tail of the output.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "finish", "description": "Call when the refactor is complete.", "input_schema": {"type": "object", "properties": {}}},
]
MAX_STEPS = 25
MAX_TOOL_CHARS = 8000

def _tool(root, task, name, a):
    if name == "list_files":
        return "\n".join(str(p.relative_to(root)) for p in context.py_files(root))
    if name == "grep":
        try:
            rx = re.compile(a["pattern"])
        except re.error as e:
            return f"bad regex: {e}"
        hits = [f"{p.relative_to(root)}:{i}: {l.strip()}" for p in context.py_files(root)
                for i, l in enumerate(p.read_text().splitlines(), 1) if rx.search(l)]
        return "\n".join(hits[:80]) + (f"\n... {len(hits)-80} more" if len(hits) > 80 else "") or "no matches"
    if name == "read_file":
        p = root / a["path"]
        if not p.is_file():
            return "file not found"
        return "\n".join(f"{i:4d}  {l}" for i, l in enumerate(p.read_text().splitlines(), 1))
    if name == "edit":
        err = edits.apply(root, [(a["path"], a["search"], a["replace"])])
        return err[0] if err else "ok"
    if name == "delete_file":
        p = (root / a["path"]).resolve()
        if root.resolve() in p.parents and p.is_file():
            p.unlink(); return "deleted"
        return "file not found"
    if name == "find_references":
        return find_references(root, a["symbol"])
    if name == "rename_symbol":
        return rename_symbol(root, a["old"], a["new"], a.get("dry_run", False))
    if name == "move_file":
        src, dst = (root / a["src"]).resolve(), (root / a["dst"]).resolve()
        if root.resolve() not in src.parents or root.resolve() not in dst.parents or not src.is_file():
            return "bad path"
        dst.parent.mkdir(parents=True, exist_ok=True); src.rename(dst); return f"moved {a['src']} -> {a['dst']}"
    if name == "edit_all":
        p = root / a["path"]
        if not p.is_file():
            return "file not found"
        t = p.read_text(); n = t.count(a["search"])
        if n == 0:
            return "0 matches; nothing changed"
        p.write_text(t.replace(a["search"], a["replace"])); return f"replaced {n} occurrence(s)"
    if name == "run_tests":
        ok, tail = grade.run_tests(root, task)
        return ("PASSED\n" if ok else "FAILED\n") + tail
    return "unknown tool"

def _agentic(root, task, preamble, tools=None, compaction=None):
    tools = tools or TOOLS
    stats = _new_stats()
    msgs = [{"role": "user", "content": f"{preamble}### TASK\n{task['instruction']}\n\nUse the tools to explore, edit, and verify. Call finish when done."}]
    steps = 0
    tool_calls = 0
    while steps < MAX_STEPS:
        steps += 1
        r, u, usd, dt = llm.call(SYSTEM, msgs, tools=tools)
        _acc(stats, u, usd, dt)
        stats["notes"]["max_prompt_tokens"] = max(stats["notes"].get("max_prompt_tokens", 0), _prompt_tokens(u))
        msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]})
        uses = [b for b in r.content if b.type == "tool_use"]
        if not uses:
            break
        results, done = [], False
        for b in uses:
            tool_calls += 1
            if b.name == "finish":
                done = True; out = "ok"
            else:
                out = _tool(root, task, b.name, b.input)
            if len(out) > MAX_TOOL_CHARS:
                out = out[:MAX_TOOL_CHARS] + f"\n...[truncated {len(out)-MAX_TOOL_CHARS} chars]"
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        msgs.append({"role": "user", "content": results})
        if done:
            break
        if compaction:
            mode, frac = compaction
            if _prompt_tokens(u) > frac * COMPACT_BUDGET:
                stats["transcript_archive"] = stats.get("transcript_archive", []) + [json.loads(json.dumps(msgs, default=str))]
                msgs = _compact(stats, msgs, mode)
    stats["notes"].update(steps=steps, tool_calls=tool_calls, hit_step_cap=steps >= MAX_STEPS)
    stats["transcript"] = {"system": SYSTEM, "messages": msgs, "pre_compaction_histories": stats.pop("transcript_archive", [])}
    return stats

# ---------------- structured tools (arm T) ----------------
def find_references(root, symbol):
    import ast as _ast
    word = re.compile(rf"\b{re.escape(symbol.split('.')[-1])}\b")
    out = {"definition": [], "import": [], "code": [], "string_or_comment": []}
    for p in context.py_files(root):
        src = p.read_text(); lines = src.splitlines()
        str_lines = set()
        try:
            for n in _ast.walk(_ast.parse(src)):
                if isinstance(n, _ast.Constant) and isinstance(n.value, str) and word.search(n.value):
                    str_lines.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        except SyntaxError:
            pass
        for i, l in enumerate(lines, 1):
            if not word.search(l):
                continue
            s_ = l.strip(); loc = f"{p.relative_to(root)}:{i}: {s_[:120]}"
            if re.match(rf"(async\s+)?(def|class)\s+{re.escape(symbol.split('.')[-1])}\b", s_):
                out["definition"].append(loc)
            elif s_.startswith(("import ", "from ")):
                out["import"].append(loc)
            elif i in str_lines or s_.startswith("#") or ("#" in l and word.search(l.split("#", 1)[1]) and not word.search(l.split("#", 1)[0])):
                out["string_or_comment"].append(loc)
            else:
                out["code"].append(loc)
    total = sum(map(len, out.values()))
    return f"{total} references to {symbol!r}\n" + "\n".join(f"## {k} ({len(v)})\n" + "\n".join(v) for k, v in out.items() if v)

def rename_symbol(root, old, new, dry_run=False):
    word = re.compile(rf"\b{re.escape(old)}\b"); report = []
    for p in context.py_files(root):
        t = p.read_text(); n = len(word.findall(t))
        if n:
            report.append(f"{p.relative_to(root)}: {n}")
            if not dry_run:
                p.write_text(word.sub(new, t))
    return ("DRY RUN " if dry_run else "") + f"renamed whole-word {old!r} -> {new!r}\n" + ("\n".join(report) or "no occurrences")

STRUCTURED_TOOLS = [t for t in TOOLS if t["name"] not in ("grep",)] + [
    {"name": "find_references", "description": "Find every whole-word reference to a symbol across the repo, grouped into definition / import / code / string_or_comment.",
     "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "rename_symbol", "description": "Rename a symbol everywhere (whole-word, all Python files incl. tests, strings and comments). Use dry_run to preview counts.",
     "input_schema": {"type": "object", "properties": {"old": {"type": "string"}, "new": {"type": "string"}, "dry_run": {"type": "boolean"}}, "required": ["old", "new"]}},
    {"name": "edit_all", "description": "Replace ALL occurrences of an exact snippet in one file; reports the match count.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "search": {"type": "string"}, "replace": {"type": "string"}}, "required": ["path", "search", "replace"]}},
    {"name": "move_file", "description": "Move/rename a file within the repo.",
     "input_schema": {"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}},
    {"name": "grep", "description": "Regex search over Python files. Returns file:line: text (max 80 hits).",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

# ---------------- procedural context (arm C) ----------------
SKILL = """## Skill: multi-file refactor (follow exactly)
1. Find ALL references to the symbol before editing: whole-word search across src AND tests, including imports, __all__, docstrings, comments, and dotted string paths like 'pkg.module.name'.
2. Change the definition, then update every reference you found. For moves, create the new module, delete the old code/file, and fix every import.
3. Run the tests.
4. Search again for the old name/path; the count must be zero (no aliases, no shims).
5. Only then call finish.
"""

def agents_md(root, task):
    repo = task["repo"]["name"]; pkg = "src/" if (root / "src").is_dir() else ""
    return f"""## AGENTS.md ({repo})
- Package code lives in `{pkg}{repo}/`; tests live in `tests/` and run with pytest (use the run_tests tool).
- Python 3.9+ style, type hints on public functions, one import per line where the file already does so.
- Public API is re-exported from `{pkg}{repo}/__init__.py`; keep `__all__` lists in sync with definitions.
- Never leave backwards-compatibility aliases or shims unless asked. Keep docstrings and comments accurate after renames.
- Prefer small, focused edits; do not reformat unrelated code.
"""

# ---------------- compaction (arm B) ----------------
COMPACT_BUDGET = 24_000
SUMMARY_PROMPT = ("You are performing a CONTEXT CHECKPOINT. Write a concise handoff summary for yourself to continue the task: "
                  "the goal, what has been changed so far (files and exact edits), what references remain to update, test status, and next steps. "
                  "Be specific about file paths and symbol names.")

def _prompt_tokens(u):
    return u["input"] + u["cache_read"] + u["cache_write"]

def _compact(stats, msgs, mode):
    if mode == "mask":
        tr_idx = [i for i, m in enumerate(msgs) if m["role"] == "user" and isinstance(m["content"], list)]
        for i in tr_idx[:-2]:
            for b in msgs[i]["content"]:
                if b.get("type") == "tool_result" and b.get("content") != "[old tool output removed]":
                    b["content"] = "[old tool output removed]"
        stats["notes"]["compactions"] = stats["notes"].get("compactions", 0) + 1
        return msgs
    hist = msgs + [{"role": "user", "content": SUMMARY_PROMPT}]
    # the last message is a user tool_result list; merge the prompt into it to keep roles alternating
    hist = msgs[:-1] + [{"role": "user", "content": msgs[-1]["content"] + [{"type": "text", "text": SUMMARY_PROMPT}]}]
    r, u, usd, dt = llm.call(SYSTEM, hist)
    _acc(stats, u, usd, dt)
    summary = _text(r)
    stats["notes"]["compactions"] = stats["notes"].get("compactions", 0) + 1
    stats["notes"].setdefault("summaries", []).append(summary[:3000])
    first = msgs[0]["content"]
    return [{"role": "user", "content": f"{first}\n\n### PROGRESS SO FAR (context was compacted)\n{summary}\n\nContinue from here."}]

def agentic(root, task):
    return _agentic(root, task, "")

def skel_retrieval(root, task):
    return _agentic(root, task, context.skeleton(root, 2) + "\n\n")

def agentic_tools(root, task):
    return _agentic(root, task, "", tools=STRUCTURED_TOOLS)

def agentic_c50(root, task):
    return _agentic(root, task, "", compaction=("summary", 0.5))

def agentic_c90(root, task):
    return _agentic(root, task, "", compaction=("summary", 0.9))

def agentic_mask(root, task):
    return _agentic(root, task, "", compaction=("mask", 0.5))

def agentic_skill(root, task):
    return _agentic(root, task, SKILL + "\n")

def agentic_agentsmd(root, task):
    return _agentic(root, task, agents_md(root, task) + "\n")

STRATEGIES = {
    "full": full, "touched": touched,
    "skel_L0": make_skeleton(0), "skel_L1": make_skeleton(1), "skel_L2": make_skeleton(2), "skel_L3": make_skeleton(3),
    "skel_retrieval": skel_retrieval, "agentic": agentic,
    "agentic_tools": agentic_tools,
    "agentic_c50": agentic_c50, "agentic_c90": agentic_c90, "agentic_mask": agentic_mask,
    "agentic_skill": agentic_skill, "agentic_agentsmd": agentic_agentsmd,
}
from .external import EXTERNAL
STRATEGIES.update(EXTERNAL)
ARMS = {
    "A": ["full", "touched", "skel_L0", "skel_L1", "skel_L2", "skel_L3", "skel_retrieval", "agentic"],
    "T": ["agentic", "agentic_tools"],
    "B": ["agentic", "agentic_c50", "agentic_c90", "agentic_mask"],
    "C": ["agentic", "agentic_skill", "agentic_agentsmd"],
    "E": list(EXTERNAL),
}
