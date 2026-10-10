"""Render docs/CASE_STUDY.md from docs/CASE_STUDY.template.md and the logged results.

Every number in the article is a {{placeholder}} filled from results/article_numbers.json (written by
cshape.report) or computed here from the raw results/*.jsonl rows via cshape.report.load(). Derived
numbers that report.py does not already publish are written to results/article_extras.json so they can
be cited. A placeholder with no value is a hard error, so the article can never ship a hand-typed stat.
Prose claims that depend on the direction of a result are guarded by `claim()` assertions.
Usage: python -m cshape.article   (also run by `make figures`)"""
import json, re
from collections import defaultdict
from pathlib import Path
from cshape import report

ROOT = Path(__file__).resolve().parent.parent
RES, DOCS = ROOT / "results", ROOT / "docs"
TEMPLATE, OUT, EXTRAS = DOCS / "CASE_STUDY.template.md", DOCS / "CASE_STUDY.md", RES / "article_extras.json"

pct = lambda x, d=0: f"{100 * x:.{d}f}%"
usd = lambda x: f"${x:.4f}" if x < 0.1 else f"${x:.2f}"
ci = lambda v: f"{pct(v['ci_lo'])}–{pct(v['ci_hi'])}"
is_hard = lambda task: bool(re.search(r"[-_]h\d\d", task or ""))

def fanout(task_id):
    """Size of a rename task, measured from its reference diff: files touched, matches of the task's
    `absent` patterns on removed lines (call sites / references), and how many removed lines contain one."""
    import yaml
    for y in (ROOT / "tasks").glob("*/*.yaml"):
        t = yaml.safe_load(y.read_text())
        if isinstance(t, dict) and t.get("id") == task_id:
            pats = [re.compile(x) for x in t["absent"]]
            rem = [ln for ln in (y.parent / t["reference"]).read_text().splitlines() if ln.startswith("-") and not ln.startswith("---")]
            return {"files": sum(1 for ln in (y.parent / t["reference"]).read_text().splitlines() if ln.startswith("diff --git")),
                    "matches": sum(len(pt.findall(ln)) for ln in rem for pt in pats),
                    "lines": sum(1 for ln in rem if any(pt.search(ln) for pt in pats))}
    raise SystemExit(f"task not found: {task_id}")

def claim(cond, msg):
    if not cond:
        raise SystemExit(f"article claim no longer holds, rewrite the prose: {msg}")

def lenient(r):
    """Code-only grading: tests pass, task check passes, no leftover reference in code (comments/strings ignored)."""
    return bool(r.get("tests_ok")) and bool(r.get("check_ok")) and (r.get("missed_code_refs") or 0) == 0

def transcript(r):
    p = ROOT / r["transcript_path"]
    return json.loads(p.read_text()).get("transcript") if p.exists() else None

def _text_blocks(content):
    if isinstance(content, str):
        return [content]
    return [b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text"]

def final_text(r):
    """Last non-empty assistant text in a run transcript (internal or external harness)."""
    t = transcript(r)
    if isinstance(t, dict) and "messages" in t:  # agentic: chat history
        items = [m["content"] for m in t["messages"] if m.get("role") == "assistant"]
    elif isinstance(t, dict):  # external harness: stdout
        return t.get("stdout") or ""
    else:  # single-shot: list of request/response pairs
        items = [x.get("response") for x in (t or []) if isinstance(x, dict)]
    for c in reversed(items):
        txt = "\n".join(x for x in _text_blocks(c) if x.strip())
        if txt.strip():
            return txt
    return ""

def quote(s, n=700):
    s = s.strip()
    s = s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"
    return "\n".join("> " + ln if ln.strip() else ">" for ln in s.splitlines())

def main():
    A = json.loads((RES / "article_numbers.json").read_text())
    pc, hl, panel = A["per_config"], A["headline"], A["arm_e_panel"]
    rows = [r for r in report.load() if not r.get("error")]
    V = {}

    # ---- per-config numbers: {{main.agentic.pass}}, {{arme.ext_aider.cps}}, {{panel.combined.n}} ...
    def put(prefix, v):
        V[f"{prefix}.n"] = str(v["n"]); V[f"{prefix}.passed"] = str(v["passed"])
        V[f"{prefix}.pass"] = pct(v["pass_rate"]); V[f"{prefix}.pass1"] = pct(v["pass_rate"], 1); V[f"{prefix}.ci"] = ci(v)
        V[f"{prefix}.cps"] = usd(v["cost_per_solve_usd"]) if v.get("cost_per_solve_usd") else "n/a"
        V[f"{prefix}.cost"] = usd(v["total_cost_usd"]); V[f"{prefix}.tools"] = f"{v['mean_tool_calls']:.1f}"
        V[f"{prefix}.comp"] = f"{v['mean_compactions']:.1f}"; V[f"{prefix}.wall"] = f"{v['mean_wall_s']:.0f}"
        V[f"{prefix}.cache"] = pct(v["cache_hit_ratio"]); V[f"{prefix}.rl"] = str(v.get("runs_rate_limited", 0))
        V[f"{prefix}.no429"] = pct(v["pass_rate_no_429"]) if v.get("pass_rate_no_429") is not None else "n/a"
        V[f"{prefix}.out"] = f"{v['mean_output']:,}"
    for k, v in pc.items():
        src, st = k.split(":", 1); put(f"{src.replace('arm_e', 'arme')}.{st}", v)
    for st, v in panel.items():
        if isinstance(v, dict) and "n" in v:
            put(f"panel.{st}", v)

    # ---- headline
    V.update({"hl.base": pct(hl["baseline_pass"]), "hl.best": pct(hl["best_pass"]), "hl.base1": pct(hl["baseline_pass"], 1),
              "hl.lift": f"{hl['lift_pp']:.0f}", "hl.lift1": f"{hl['lift_pp']:.1f}",
              "hl.base_cps": usd(hl["baseline_cost_per_solve"]), "hl.best_cps": usd(hl["best_cost_per_solve"]),
              "hl.ratio": f"{hl['baseline_cost_per_solve'] / hl['best_cost_per_solve']:.0f}",
              "hl.n": str(hl["n_baseline"]), "hl.base_ci": f"{pct(hl['baseline_ci'][0])}–{pct(hl['baseline_ci'][1])}",
              "hl.best_ci": f"{pct(hl['best_ci'][0], 1)}–{pct(hl['best_ci'][1])}"})
    claim(A["final_run"]["complete"], "final run incomplete")
    claim(hl["lift_pp"] >= 20 and hl["best_cost_per_solve"] < hl["baseline_cost_per_solve"], "H7 headline")
    V["ledger"] = f"${A['ledger_usd']:.2f}"; V["total_runs"] = f"{A['total_runs']:,}"
    V["logged_cost"] = f"${A['total_logged_cost_usd']:.2f}"
    sr = A["spend_reconciliation"]; V["recon.logged"] = f"${sr['logged_usd']:.2f}"; V["recon.gap"] = f"${sr['unlogged_gap_usd']:.2f}"
    V["dup.cost"] = f"${A['duplicates_dropped']['cost_usd']:.2f}"; V["dup.rows"] = str(A["duplicates_dropped"]["rows"])
    ch = json.loads((RES / "combined_choice.json").read_text())["choice"]
    V["choice"] = ", ".join(f"{k} = {v}" for k, v in ch.items())

    # ---- tasks
    final = [r for r in rows if r["_file"] == "final"]
    tasks = sorted({r["task"] for r in final})
    by_repo = defaultdict(set)
    for t in tasks:
        by_repo[t.split("-")[0]].add(t)
    V["n_tasks"] = str(len(tasks)); V["n_hard"] = str(sum(map(is_hard, tasks))); V["n_base"] = str(len(tasks) - sum(map(is_hard, tasks)))
    V["n_seeds_final"] = str(len({r["seed"] for r in final}))
    for repo, ts in by_repo.items():
        V[f"tasks.{repo}"] = str(len(ts))

    # per-task table for the final run
    cell = defaultdict(lambda: [0, 0])
    for r in final:
        c = cell[(r["task"], r["strategy"])]; c[0] += bool(r["passed"]); c[1] += 1
    lines = ["| Task | Tier | Naive (full repo) | Combined harness |", "|---|---|---|---|"]
    for t in sorted(tasks, key=lambda t: (cell[(t, 'full')][0] / max(1, cell[(t, 'full')][1]), t)):
        f, c = cell[(t, "full")], cell[(t, "combined")]
        lines.append(f"| `{t}` | {'hard' if is_hard(t) else 'base'} | {f[0]}/{f[1]} | {c[0]}/{c[1]} |")
    V["final_task_table"] = "\n".join(lines)
    V["full_zero_tasks"] = str(sum(1 for t in tasks if cell[(t, 'full')][0] == 0))
    V["full_perfect_tasks"] = str(sum(1 for t in tasks if cell[(t, 'full')][0] == cell[(t, 'full')][1]))

    # ---- grader sensitivity (code-only grading)
    ex = {}
    for key, tid in (("h02", "tinydb-h02-rename-table-insert"), ("h03", "marshmallow-h03-rename-validationerror")):
        f = fanout(tid); ex[f"fanout_{key}"] = f
        for k, v in f.items():
            V[f"fan.{key}.{k}"] = str(v)
    for st in ("full", "combined"):
        rs = [r for r in final if r["strategy"] == st]
        k = sum(map(lenient, rs)); ex[f"final_{st}_lenient_pass"] = round(k / len(rs), 4)
        lo, hi = report.wilson(k, len(rs)); ex[f"final_{st}_lenient_ci"] = [round(lo, 4), round(hi, 4)]
        ex[f"final_{st}_comment_only_fails"] = sum(1 for r in rs if not r["passed"] and lenient(r))
        V[f"len.{st}"] = pct(k / len(rs)); V[f"len.{st}.ci"] = f"{pct(lo)}–{pct(hi)}"
        V[f"len.{st}.comment_only"] = str(ex[f"final_{st}_comment_only_fails"])
    claim(ex["final_combined_lenient_pass"] - ex["final_full_lenient_pass"] >= 0.2, "lift survives code-only grading")
    V["len.lift"] = f"{100 * (ex['final_combined_lenient_pass'] - ex['final_full_lenient_pass']):.0f}"

    # ---- base vs hard tier, main run
    main_rows = [r for r in rows if r["_file"] == "main"]
    tier = {}
    order = ["full", "touched", "skel_L1", "skel_retrieval", "agentic", "agentic_tools", "agentic_skill", "agentic_mask_tight"]
    tl = ["| Config | Base tasks | Hard tasks |", "|---|---|---|"]
    for st in order:
        b = [r for r in main_rows if r["strategy"] == st and not is_hard(r["task"])]
        h = [r for r in main_rows if r["strategy"] == st and is_hard(r["task"])]
        pb, ph = sum(r["passed"] for r in b) / len(b), sum(r["passed"] for r in h) / len(h)
        tier[st] = {"base_pass": round(pb, 4), "base_n": len(b), "hard_pass": round(ph, 4), "hard_n": len(h)}
        V[f"tier.{st}.base"] = pct(pb); V[f"tier.{st}.hard"] = pct(ph)
        tl.append(f"| {report.LABEL[st]} | {pct(pb)} (n={len(b)}) | {pct(ph)} (n={len(h)}) |")
    V["tier_table"] = "\n".join(tl); ex["tier_pass_main"] = tier

    # ---- tool design detail: the 468-reference rename
    h03 = lambda st: [r for r in main_rows if r["strategy"] == st and r["task"] == "marshmallow-h03-rename-validationerror"]
    for st in ("agentic", "agentic_tools"):
        rs = h03(st); V[f"h03.{st}"] = f"{sum(r['passed'] for r in rs)}/{len(rs)}"
        V[f"h03.{st}.capped"] = str(sum(bool(r["notes"].get("hit_step_cap")) for r in rs))
        V[f"h03.{st}.calls"] = f"{sum(r['notes'].get('tool_calls', 0) for r in rs) / len(rs):.0f}"
        V[f"h03.{st}.peak"] = f"{max(r['notes'].get('max_prompt_tokens', 0) for r in rs):,}"
        ex[f"h03_{st}"] = {"passed": sum(r["passed"] for r in rs), "n": len(rs), "hit_step_cap": int(V[f"h03.{st}.capped"]),
                           "mean_tool_calls": float(V[f"h03.{st}.calls"]), "peak_prompt_tokens": max(r["notes"].get("max_prompt_tokens", 0) for r in rs)}
    claim(int(V["h03.agentic.capped"]) == len(h03("agentic")), "every grep-agent h03 run hit the step cap")
    claim(pc["main:skel_retrieval"]["cost_per_solve_usd"] > 1.8 * pc["main:agentic"]["cost_per_solve_usd"], "skeleton doubles agent cost")
    V["arme.ext_aider.n_no429"] = str(pc["arm_e:ext_aider"]["n"] - pc["arm_e:ext_aider"]["runs_rate_limited"])
    V["tools.ratio"] = f"{pc['main:agentic']['cost_per_solve_usd'] / pc['main:agentic_tools']['cost_per_solve_usd']:.1f}"
    V["tools.callratio"] = f"{pc['main:agentic']['mean_tool_calls'] / pc['main:agentic_tools']['mean_tool_calls']:.1f}"
    V["arme.cc_vs_combined"] = f"{panel['ext_claude_code']['cost_per_solve_usd'] / panel['combined']['cost_per_solve_usd']:.1f}"
    claim(pc["main:agentic_tools"]["pass_rate"] >= pc["main:agentic"]["pass_rate"], "H4 direction")
    claim(pc["main:agentic_mask_tight"]["pass_rate"] > pc["main:agentic_c50_tight"]["pass_rate"], "H5 mask > c50 tight")
    claim(pc["main:agentic_c90_tight"]["pass_rate"] > pc["main:agentic_c50_tight"]["pass_rate"], "H5 c90 > c50 tight")
    claim(abs(pc["main:touched"]["pass_rate"] - pc["main:full"]["pass_rate"]) < 0.05, "H1: touched ~ full")
    claim(pc["main:skel_L1"]["pass_rate"] >= pc["main:skel_L2"]["pass_rate"], "H2: L2 adds nothing over L1")
    claim(pc["main:agentic_skill"]["pass_rate"] == pc["main:agentic"]["pass_rate"], "H6: skill same pass as none")
    single = ["full", "touched", "skel_L0", "skel_L1", "skel_L2", "skel_L3"]
    best_single = max(pc[f"main:{s}"]["pass_rate"] for s in single)
    claim(min(pc["main:agentic"]["pass_rate"], pc["main:skel_retrieval"]["pass_rate"]) > best_single, "H3")
    V["best_single"] = pct(best_single)
    sf = sum(pc[f"main:{s}"]["fail_missed_caller"] for s in single); st_ = sum(sum(pc[f"main:{s}"][f"fail_{c}"] for c in report.FAILS) for s in single)
    V["single.missed_share"] = pct(sf / st_); ex["single_shot_missed_caller_share"] = round(sf / st_, 4)

    # ---- failure table (main run, selected configs)
    cols = ["missed_caller", "broken_import", "output_truncated", "no_edit"]
    ft = ["| Config | Failed runs | " + " | ".join(c.replace("_", " ") for c in cols) + " |", "|---|---|" + "---|" * len(cols)]
    for st in ["full", "touched", "skel_L0", "skel_L2", "skel_retrieval", "agentic", "agentic_tools", "agentic_c50_tight"]:
        v = pc[f"main:{st}"]; tot = sum(v[f"fail_{c}"] for c in report.FAILS)
        ft.append(f"| {report.LABEL[st]} | {tot} of {v['n']} | " + " | ".join(str(v[f'fail_{c}']) for c in cols) + " |")
    V["failure_table"] = "\n".join(ft)

    # ---- real transcript excerpts (pulled, never typed)
    def pick(f, st, task, cat=None, seed=None, src=None):
        for r in sorted(rows, key=lambda r: r["seed"]):
            if r["_file"] == f and r["strategy"] == st and r["task"] == task and (cat is None or r["failure_category"] == cat) \
               and (seed is None or r["seed"] == seed) and (src is None or r["_src"] == src) and not r["passed"]:
                return r
        raise SystemExit(f"excerpt row missing: {f} {st} {task}")
    r = pick("final", "full", "tinydb-h02-rename-table-insert", "missed_caller")
    V["ex.h02.missed"] = str(r["missed_callers"]); V["ex.h02.seed"] = str(r["seed"])
    V["ex.h02.refs"] = "\n".join(f"    {m}" for m in r["missed"][:4])
    r = pick("main", "skel_L3", "marshmallow-h03-rename-validationerror", "no_edit")
    gu = final_text(r).split("Run this from")[0]
    claim(gu.strip(), "give-up excerpt has text"); V["ex.giveup"] = quote(gu, 600); V["ex.giveup.seed"] = str(r["seed"])
    fz = [r for r in rows if r["_file"] == "main" and r["strategy"] == "agentic_agentsmd" and r["task"] == "tinydb-t05-rename-freeze"
          and not r["passed"] and "verb" in final_text(r)]
    claim(fz, "an agent explained the leftover 'freeze' is a verb"); r = fz[0]
    V["ex.freeze"] = quote(final_text(r), 400); V["ex.freeze.ref"] = r["missed"][0]; V["ex.freeze.seed"] = str(r["seed"])
    r = pick("arm_e", "ext_aider", "tinydb-t01-rename-lrucache")
    txt = final_text(r); i = txt.find("If the grep finds")
    claim(i >= 0, "aider closing line present"); V["ex.aider"] = quote(txt[i:].split("Tokens:")[0], 300)
    V["ex.aider.missed"] = str(r["missed_callers"])

    EXTRAS.write_text(json.dumps(ex, indent=1))
    tpl = TEMPLATE.read_text()
    missing = sorted(set(re.findall(r"\{\{([^}]+)\}\}", tpl)) - set(V))
    if missing:
        raise SystemExit(f"template placeholders with no value: {missing}")
    body = re.sub(r"\{\{([^}]+)\}\}", lambda m: V[m.group(1)], tpl)
    OUT.write_text("<!-- GENERATED by `python -m cshape.article` from docs/CASE_STUDY.template.md + results/. Edit the template, not this file. -->\n" + body)
    print(f"{OUT.relative_to(ROOT)}: {len(body.split())} words, {len(set(re.findall(r'{{([^}]+)}}', tpl)))} data placeholders")

if __name__ == "__main__":
    main()
