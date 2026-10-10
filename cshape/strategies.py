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
    stats["notes"]["apply_errors"] = edits.apply(root, blocks)
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
    if name == "run_tests":
        ok, tail = grade.run_tests(root, task)
        return ("PASSED\n" if ok else "FAILED\n") + tail
    return "unknown tool"

def _agentic(root, task, preamble):
    stats = _new_stats()
    msgs = [{"role": "user", "content": f"{preamble}### TASK\n{task['instruction']}\n\nUse the tools to explore, edit, and verify. Call finish when done."}]
    steps = 0
    tool_calls = 0
    while steps < MAX_STEPS:
        steps += 1
        r, u, usd, dt = llm.call(SYSTEM, msgs, tools=TOOLS)
        _acc(stats, u, usd, dt)
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
    stats["notes"].update(steps=steps, tool_calls=tool_calls, hit_step_cap=steps >= MAX_STEPS)
    stats["transcript"] = {"system": SYSTEM, "messages": msgs}
    return stats

def agentic(root, task):
    return _agentic(root, task, "")

def skel_retrieval(root, task):
    return _agentic(root, task, context.skeleton(root, 2) + "\n\n")

STRATEGIES = {
    "full": full, "touched": touched,
    "skel_L0": make_skeleton(0), "skel_L1": make_skeleton(1), "skel_L2": make_skeleton(2), "skel_L3": make_skeleton(3),
    "skel_retrieval": skel_retrieval, "agentic": agentic,
}
