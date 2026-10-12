"""Select the FINAL COMBINED config from main-run results, by a rule fixed before the final run:
for each arm, pick the option with the highest pass rate; break exact ties by lower cost per solved task.
Writes results/combined_choice.json, which the `combined` strategy reads."""
import json
from pathlib import Path
from .report import load, summarize

ROOT = Path(__file__).resolve().parent.parent
OPTIONS = {
    "layout": {"agentic": "agentic", "skeleton_L2_upfront": "skel_retrieval"},
    "tools": {"raw": "agentic", "structured": "agentic_tools"},
    "compaction": {"none": "agentic", "summary50": "agentic_c50", "summary90": "agentic_c90", "mask": "agentic_mask"},
    "procedural": {"none": "agentic", "skill": "agentic_skill", "agents_md": "agentic_agentsmd"},
}

def main():
    rows = [r for r in load() if r["_file"] == "main"]
    choice, evidence = {}, {}
    for arm, opts in OPTIONS.items():
        scored = []
        for opt, strat in opts.items():
            rs = [r for r in rows if r["strategy"] == strat]
            s = summarize(rs)
            scored.append((s["pass_rate"], -(s["cost_per_solve_usd"] or 1e9), opt, s["n"]))
        scored.sort(reverse=True)
        choice[arm] = scored[0][2]
        evidence[arm] = [dict(option=o, pass_rate=p, cost_per_solve=-c, n=n) for p, c, o, n in scored]
    out = {"rule": "per arm: max pass rate, exact ties -> lower cost per solve (main runs incl. hard tasks)", "choice": choice, "evidence": evidence}
    (ROOT / "results" / "combined_choice.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(choice))

if __name__ == "__main__":
    main()
