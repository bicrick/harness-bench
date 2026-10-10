"""Rebuild every derived artifact from raw logs in results/*.jsonl:
  results/summary.csv, results/failures.csv, results/article_numbers.json, results/excerpts/*.md, figures/*.png
Usage: make figures   (python -m cshape.report)"""
import csv, json, math, random
from collections import Counter, defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RES, FIG = ROOT / "results", ROOT / "figures"
MAIN = "main"  # primary run file; 'pilot' and 'final' summarized too
ARMS = {
    "layout": ["full", "touched", "skel_L0", "skel_L1", "skel_L2", "skel_L3", "skel_retrieval", "agentic"],
    "ladder": ["skel_L0", "skel_L1", "skel_L2", "skel_L3", "full"],
    "tools": ["agentic", "agentic_tools"],
    "compaction": ["agentic", "agentic_c50", "agentic_c90", "agentic_mask"],
    "skills": ["agentic", "agentic_skill", "agentic_agentsmd"],
    "compaction_tight": ["agentic", "agentic_c50_tight", "agentic_c90_tight", "agentic_mask_tight"],
}
LABEL = {"full": "full repo (naive)", "touched": "touched files (oracle)", "skel_L0": "skeleton L0 tree", "skel_L1": "L1 +imports",
         "skel_L2": "L2 +signatures", "skel_L3": "L3 +docstrings", "skel_retrieval": "skeleton + tools", "agentic": "agentic grep/read",
         "agentic_tools": "agentic + structured tools", "agentic_c50": "summarize @50%", "agentic_c90": "summarize @90%",
         "agentic_mask": "drop old tool output", "agentic_c50_tight": "summarize @50% (12k)", "agentic_c90_tight": "summarize @90% (12k)",
         "agentic_mask_tight": "drop old output (12k)", "agentic_skill": "refactor skill", "agentic_agentsmd": "AGENTS.md",
         "combined": "best combined harness", "ext_claude_code": "Claude Code (closed)", "ext_opencode": "OpenCode",
         "ext_aider": "Aider", "ext_mini_swe_agent": "mini-swe-agent"}
FAILS = ["missed_caller", "broken_import", "apply_failure", "output_truncated", "no_edit", "test_failure_other", "check_failed", "context_overflow", "error"]
STYLE = dict(color="#3B6EA8", accent="#D2691E", grid="#DDDDDD")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": STYLE["grid"], "axes.axisbelow": True, "figure.dpi": 150})

def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))

MERGE_INTO_MAIN = {"hard": "main", "hard2": "main"}

def last_stop_reason(r):
    """stop_reason of the final model response in the run transcript (None if unknown)."""
    if (r.get("notes") or {}).get("last_stop_reason"):
        return r["notes"]["last_stop_reason"]
    tp = r.get("transcript_path")
    if not tp or not (ROOT / tp).exists():
        return None
    try:
        t = json.loads((ROOT / tp).read_text()).get("transcript", [])
    except Exception:
        return None
    if not isinstance(t, list):
        return None
    for x in reversed(t):
        if not isinstance(x, dict):
            continue
        sr = x.get("response", {}).get("stop_reason") if isinstance(x.get("response"), dict) else x.get("stop_reason")
        if sr:
            return sr
    return None

def retag(r):
    """The harness tagger calls a run 'no_edit' when it produced no diff. If the final response hit the
    16k output cap, the model was mid-answer, so tag it 'output_truncated' instead (derived from the transcript)."""
    if not r.get("passed") and r.get("failure_category") in ("no_edit", "apply_failure") and last_stop_reason(r) == "max_tokens":
        r["failure_category"] = "output_truncated"
    return r

def load():
    """All result rows. hard*.jsonl are merged into "main". Duplicate (group, task, strategy, seed)
    rows (two resumable runs can cover the same job) are dropped, keeping the first non-error row."""
    best = {}
    files = sorted(RES.glob("*.jsonl"), key=lambda f: (f.stem not in ("main", "final", "arm_e"), f.name))
    for f in files:
        if f.name.startswith("archive_"):
            continue
        for line in f.open():
            r = retag(json.loads(line)); r["_file"] = MERGE_INTO_MAIN.get(f.stem, f.stem)
            key = (r["_file"], r.get("task"), r.get("strategy"), r.get("seed"))
            if key not in best or (best[key].get("error") and not r.get("error")):
                best[key] = r
    return list(best.values())

def summarize(rs):
    n = len(rs); k = sum(bool(r.get("passed")) for r in rs)
    cost = sum(r.get("cost_usd", 0) for r in rs)
    tok = lambda key: sum(r.get("tokens", {}).get(key, 0) for r in rs) / n
    lo, hi = wilson(k, n)
    fc = Counter(r.get("failure_category") for r in rs if not r.get("passed"))
    return dict(n=n, passed=k, pass_rate=round(k / n, 4), ci_lo=round(lo, 4), ci_hi=round(hi, 4),
                mean_missed_callers=round(sum(r.get("missed_callers") or 0 for r in rs) / n, 3),
                median_missed_callers=sorted(r.get("missed_callers") or 0 for r in rs)[n // 2],
                mean_missed_code_refs=round(sum(r.get("missed_code_refs") or 0 for r in rs) / n, 3),
                mean_diff_lines=round(sum((r.get("diff", {}).get("added", 0) + r.get("diff", {}).get("removed", 0)) for r in rs) / n, 1),
                mean_input=round(tok("input")), mean_cache_read=round(tok("cache_read")), mean_cache_write=round(tok("cache_write")),
                mean_output=round(tok("output")), total_cost_usd=round(cost, 4), mean_cost_usd=round(cost / n, 5),
                cost_per_solve_usd=round(cost / k, 5) if k else None,
                mean_wall_s=round(sum(r.get("wall_s", 0) for r in rs) / n, 1),
                mean_tool_calls=round(sum(r.get("notes", {}).get("tool_calls", 0) for r in rs) / n, 1),
                mean_compactions=round(sum(r.get("notes", {}).get("compactions", 0) for r in rs) / n, 2),
                **{f"fail_{c}": fc.get(c, 0) for c in FAILS})

def bar(ax, ss, keys, title):
    x = range(len(keys)); s = [ss[k] for k in keys]
    ax.bar(x, [v["pass_rate"] for v in s], color=[STYLE["accent"] if k in ("full", "combined") else STYLE["color"] for k in keys],
           yerr=[[v["pass_rate"] - v["ci_lo"] for v in s], [v["ci_hi"] - v["pass_rate"] for v in s]], capsize=3)
    for i, v in enumerate(s):
        ax.text(i, 0.02, f"${v['cost_per_solve_usd']:.4f}/solve" if v["cost_per_solve_usd"] else "-", ha="center", fontsize=7, rotation=90, color="white")
    ax.set_xticks(list(x)); ax.set_xticklabels([LABEL.get(k, k) for k in keys], rotation=30, ha="right")
    ax.set_ylim(0, 1.05); ax.set_ylabel("pass rate (95% Wilson CI)"); ax.set_title(title)

def excerpt(r, maxlen=1200):
    t = json.loads((ROOT / r["transcript_path"]).read_text())["transcript"]
    if not t:
        body = f"(no transcript; error: {r.get('error', '')[:300]})"
    elif isinstance(t, dict) and "messages" not in t:
        body = "Harness stdout (tail):\n" + (t.get("stdout") or "")[-maxlen:]
    elif isinstance(t, dict):
        msgs = t["messages"]
        last_text = ""
        for m in reversed(msgs):
            if m["role"] == "assistant":
                for b in m["content"]:
                    if b.get("type") == "text" and b.get("text", "").strip():
                        last_text = b["text"]; break
            if last_text:
                break
        calls = [f"{b['name']}({json.dumps(b.get('input'))[:100]})" for m in msgs if m["role"] == "assistant" for b in m["content"] if b.get("type") == "tool_use"]
        body = "Tool calls:\n" + "\n".join(f"- {c}" for c in calls[:15]) + ("\n..." if len(calls) > 15 else "") + f"\n\nFinal message:\n{last_text[:600]}"
    if t and isinstance(t, list):
        resp = "".join(b.get("text", "") for b in t[-1]["response"] if b.get("type") == "text")
        body = "Model output (truncated):\n" + resp[:maxlen]
    return (f"### {r['task']} / {r['strategy']} / seed {r['seed']} -> {r.get('failure_category')}\n"
            f"Leftover refs: {r.get('missed', [])[:3]}\nApply errors: {r.get('notes', {}).get('apply_errors', [])[:3]}\n\n```\n{body}\n```\n")

def main():
    rows = load(); FIG.mkdir(exist_ok=True); (RES / "excerpts").mkdir(exist_ok=True)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["_file"], r["strategy"])].append(r)
    summ = {k: summarize(v) for k, v in sorted(groups.items())}
    with open(RES / "summary.csv", "w", newline="") as f:
        w = None
        for (src, st), s in summ.items():
            row = dict(source=src, strategy=st, label=LABEL.get(st, st), **s)
            if not w:
                w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader()
            w.writerow(row)
    # per-task-kind and per-repo breakdown for main
    with open(RES / "breakdown.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["source", "strategy", "repo", "n", "pass_rate"])
        g2 = defaultdict(list)
        for r in rows:
            g2[(r["_file"], r["strategy"], r["task"].split("-")[0])].append(r)
        for (src, st, repo), rs in sorted(g2.items()):
            w.writerow([src, st, repo, len(rs), round(sum(bool(x.get("passed")) for x in rs) / len(rs), 3)])
    main_s = {st: s for (src, st), s in summ.items() if src == MAIN}
    numbers = {"model": "claude-haiku-5-5", "total_runs": len(rows), "total_logged_cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 4),
               "ledger_usd": json.loads((RES / "ledger.json").read_text())["total_usd"] if (RES / "ledger.json").exists() else None,
               "spend_reconciliation": {k: v for k, v in (json.loads((RES / "integrity.json").read_text()) if (RES / "integrity.json").exists() else {}).items()
                                        if k in ("ledger_usd", "logged_usd", "unlogged_gap_usd", "call_attribution", "unattributed_pre_call_log_usd", "note")},
               "per_config": {f"{src}:{st}": s for (src, st), s in summ.items()}}
    if main_s:
        for arm, keys in ARMS.items():
            keys = [k for k in keys if k in main_s]
            if keys:
                fig, ax = plt.subplots(figsize=(max(5, 1.0 * len(keys) + 2), 4.2))
                bar(ax, main_s, keys, f"{arm}: pass rate by config (Haiku 5.5, n={main_s[keys[0]]['n']} each)")
                fig.tight_layout(); fig.savefig(FIG / f"arm_{arm}.png"); plt.close(fig)
        # Pareto
        allc = {**{k: v for k, v in main_s.items()}, **{f"final:{st}": s for (src, st), s in summ.items() if src == "final"}}
        pts = [(k, v["cost_per_solve_usd"], v["pass_rate"]) for k, v in allc.items() if v["cost_per_solve_usd"]]
        front, best = [], -1
        for k, c, p in sorted(pts, key=lambda t: (t[1], -t[2])):
            if p > best:
                front.append((k, c, p)); best = p
        from matplotlib.ticker import FuncFormatter, NullFormatter
        fig, ax = plt.subplots(figsize=(9, 6))
        for k, c, p in pts:
            on = k in [f[0] for f in front]
            ax.scatter(c, p, color=STYLE["accent"] if on else STYLE["color"], s=40 if on else 25, zorder=3)
        ax.plot([f[1] for f in front], [f[2] for f in front], color=STYLE["accent"], lw=1, ls="--")
        ax.set_xscale("log"); ax.set_xlabel("cost per solved task (USD, log scale)"); ax.set_ylabel("pass rate")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}")); ax.xaxis.set_minor_formatter(NullFormatter())
        xs = [c for _, c, _ in pts]; ax.set_xlim(min(xs) / 1.4, max(xs) * 2.2)
        texts = [ax.text(c, p, LABEL.get(k.split(":")[-1], k), fontsize=7.5) for k, c, p in pts]
        try:
            from adjustText import adjust_text  # requirements.txt; de-overlaps labels with leader lines
            adjust_text(texts, x=xs, y=[p for _, _, p in pts], ax=ax, arrowprops=dict(arrowstyle="-", lw=0.4, color="0.55"))
        except ImportError:
            pass
        ax.set_title("Cost/accuracy frontier, all configs (Haiku 5.5)"); fig.tight_layout(); fig.savefig(FIG / "pareto.png"); plt.close(fig)
        numbers["pareto_frontier"] = [f[0] for f in front]
        # failure taxonomy
        keys = list(main_s)
        fig, ax = plt.subplots(figsize=(10, 4.5)); bottom = [0] * len(keys)
        cmap = plt.get_cmap("tab10")
        for i, c in enumerate(FAILS):
            vals = [main_s[k][f"fail_{c}"] for k in keys]
            if sum(vals):
                ax.bar(range(len(keys)), vals, bottom=bottom, label=c, color=cmap(i)); bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xticks(range(len(keys))); ax.set_xticklabels([LABEL.get(k, k) for k in keys], rotation=35, ha="right")
        ax.set_ylabel("failed runs"); ax.set_title("Failure taxonomy by config"); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(FIG / "failures.png"); plt.close(fig)
        with open(RES / "failures.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["strategy"] + FAILS)
            for k in keys:
                w.writerow([k] + [main_s[k][f"fail_{c}"] for c in FAILS])
        # excerpts: one per failure category (deterministic sample)
        rnd = random.Random(0)
        fails = [r for r in rows if r["_file"] == MAIN and not r.get("passed") and r.get("transcript_path")]
        out = ["# Failure excerpts (auto-generated by cshape.report; deterministic sample)\n"]
        for c in FAILS:
            cand = [r for r in fails if r.get("failure_category") == c]
            for r in rnd.sample(cand, min(2, len(cand))):
                out.append(excerpt(r))
        (RES / "excerpts" / "failures.md").write_text("\n".join(out))
    # headline: naive baseline vs best combined
    final_s = {st: s for (src, st), s in summ.items() if src == "final"}
    base = final_s.get("full") or main_s.get("full")
    best_key = "combined" if "combined" in final_s else (max(main_s, key=lambda k: (main_s[k]["pass_rate"], -(main_s[k]["cost_per_solve_usd"] or 9))) if main_s else None)
    best = final_s.get("combined") or (main_s.get(best_key) if best_key else None)
    if base and best:
        numbers["headline"] = dict(baseline="full", best=best_key, baseline_pass=base["pass_rate"], best_pass=best["pass_rate"],
                                   lift_pp=round(100 * (best["pass_rate"] - base["pass_rate"]), 1),
                                   baseline_cost_per_solve=base["cost_per_solve_usd"], best_cost_per_solve=best["cost_per_solve_usd"],
                                   baseline_ci=[base["ci_lo"], base["ci_hi"]], best_ci=[best["ci_lo"], best["ci_hi"]],
                                   n_baseline=base["n"], n_best=best["n"])
        fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
        names = ["naive baseline\nfull repo,\nsingle-shot", "best harness\n" + LABEL.get(best_key, best_key).replace(" + ", "\n+ ")]
        axes[0].bar(names, [base["pass_rate"], best["pass_rate"]], color=[STYLE["accent"], STYLE["color"]],
                    yerr=[[base["pass_rate"] - base["ci_lo"], best["pass_rate"] - best["ci_lo"]], [base["ci_hi"] - base["pass_rate"], best["ci_hi"] - best["pass_rate"]]], capsize=4)
        axes[0].set_ylim(0, 1.05); axes[0].set_title("pass rate (95% CI)")
        axes[1].bar(names, [base["cost_per_solve_usd"], best["cost_per_solve_usd"]], color=[STYLE["accent"], STYLE["color"]])
        axes[1].set_title("cost per solved task (USD)")
        for i, v in enumerate([base["pass_rate"], best["pass_rate"]]):
            axes[0].text(i, v / 2, f"{100 * v:.0f}%", ha="center", color="white", fontweight="bold")
        for i, v in enumerate([base["cost_per_solve_usd"], best["cost_per_solve_usd"]]):
            axes[1].text(i, v, f"${v:.4f}", ha="center", va="bottom")
        for ax in axes:
            ax.tick_params(axis="x", labelsize=9)
        axes[1].set_ylim(0, 1.15 * max(base["cost_per_solve_usd"], best["cost_per_solve_usd"]))
        fig.text(0.5, 0.005, f"n = {base['n']} vs {best['n']} runs; multi-file refactors on tinydb, marshmallow, itsdangerous", ha="center", fontsize=8, color="#555555")
        fig.suptitle("Same model (Haiku 5.5), better harness"); fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(FIG / "headline.png"); plt.close(fig)
    # arm E: real harnesses vs naive vs best (same tasks only)
    e_s = {st: s for (src, st), s in summ.items() if src == "arm_e"}
    if e_s and main_s:
        e_tasks = {r["task"] for r in rows if r["_file"] == "arm_e"}
        def sub(src, st):
            rs = [r for r in rows if r["_file"] == src and r["strategy"] == st and r["task"] in e_tasks and r["seed"] == 0]
            return summarize(rs) if rs else None
        panel = {"full": sub(MAIN, "full")}
        panel.update({k: e_s[k] for k in sorted(e_s)})
        bk = "combined" if final_s.get("combined") else best_key
        if bk:
            panel[bk] = sub("final" if final_s.get("combined") else MAIN, bk)
        panel = {k: v for k, v in panel.items() if v}
        fig, ax = plt.subplots(figsize=(8, 4.2)); bar(ax, panel, list(panel), "Real harnesses vs ours on Haiku 5.5 (seed 0, same tasks)")
        fig.tight_layout(); fig.savefig(FIG / "arm_E_real_harnesses.png"); plt.close(fig)
        numbers["arm_e_panel"] = panel
    (RES / "article_numbers.json").write_text(json.dumps(numbers, indent=1))
    print(f"{len(rows)} runs -> results/summary.csv, results/article_numbers.json, figures/*.png")
    for (src, st), s in summ.items():
        print(f"{src:<7} {st:<17} n={s['n']:<3} pass={s['pass_rate']:.2f} [{s['ci_lo']:.2f},{s['ci_hi']:.2f}] missed={s['mean_missed_callers']} $/solve={s['cost_per_solve_usd']} calls={s['mean_tool_calls']} compact={s['mean_compactions']}")

if __name__ == "__main__":
    main()
