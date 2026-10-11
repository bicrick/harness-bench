# SWE-bench Verified pilot: 6 harnesses x 10 tasks (claude-haiku-5-5)

Pilot = the first 10 instances of the pinned 50-task subset (`results/swebench/subset.json`, seed 20261010): 2 astropy + 8 django. Every harness used `claude-haiku-5-5`, graded with the official SWE-bench harness. Generated 2026-10-10 23:10 CDT from `scripts/swebench_tokens.py` + `scripts/swebench_pilot_report.py 10`.

| harness | done | solved | pass rate | $ total | $/solve | tokens/task | tokens/solve | median wall s/task |
|---|---|---|---|---|---|---|---|---|
| cursor | 10/10 | 9 | 90% | 0.113 | 0.0125 | 508,583 | 565,092 | 55 |
| mini_swe_agent | 10/10 | 8 | 80% | 0.071 | 0.0089 | 226,985 | 283,732 | 76 |
| swe_agent | 10/10 | 8 | 80% | 0.113 | 0.0141 | 335,568 | 419,460 | 394 |
| opencode | 10/10 | 8 | 80% | 0.034 | 0.0043 | 88,494 | 110,618 | 46 |
| aider | 10/10 | 8 | 80% | 1.129 | 0.1411 | 249,397 | 311,746 | 120 |
| claude_code | 10/10 | 8 | 80% | 0.088 | 0.0110 | 301,608 | 377,010 | 78 |

Tokens = input + output + cache read + cache write, summed over every model call (from the cost proxy's per-call log). $/solve = harness spend / tasks resolved.

## What the pilot says

- Pass rate is flat: five harnesses solve 8/10 and Cursor solves 9/10. Ten tasks can't separate them, which is what the full 50 is for.
- Cost is not flat. Aider spent about $1.13 on 10 tasks ($0.14/solve), 10-30x everyone else, because it stuffs large repo maps and whole files into the prompt (one seaborn task in Stage 2 peaked at 172k prompt tokens). OpenCode is the cheapest at about $0.004/solve and about 110k tokens per solve, roughly 3-5x leaner than Claude Code, SWE-agent or Cursor for the same pass rate.
- Total pilot API spend was about $1.46 (Cursor excluded, see below).

## Caveats and deviations (full log: `~/sbr-deviations.md` on the box)

- **Cursor cost is an estimate.** The Cursor CLI bills through Cursor, not the proxy, so its rows have usd=0. Tokens come from the CLI's stream-json usage block and $ is estimated at Haiku 5.5's lower price tier (a lower bound). Cursor was re-run with a clean per-run HOME/config so no account plugins, MCP servers, skills or rules load (they had added ~18-38 min of startup per task over a blocked SSH port). One Cursor pilot task (django-10554) still took 29 min.
- **Wall time is not comparable across harnesses in the pilot.** Early pairs ran sequentially under Docker's slow `vfs` driver; later pairs ran in parallel on `fuse-overlayfs` with no CPU/memory limits. SWE-agent's ~6.5 min median mostly reflects that. From Stage 2 on, rows carry `concurrency_regime="slots3_cpus2_mem4g"` (3 agent runs box-wide, 2 CPU / 4 GB per container), and only those rows should be used for wall-time comparisons.
- SWE-agent needed `temperature: 1.0`, `top_p: null` (Haiku 5.5 rejects temperature 0) and a 900 s runtime startup timeout. These are box config changes, not sbr code changes.
- Five known-broken Verified instances (including django-10097) are excluded from the subset (SWE-bench #267). django-10554 replaces django-10097.
- Error and grade-failed rows are retried automatically. Eight old-regime rows that hit HTTP 429s under parallel load are queued for re-runs (`results/swebench/rerun_queue.json`), and the latest row wins.

## Next

Stage 2 (all 50 tasks, all six harnesses, $45 hard cap) is running. This doc gets the full-run numbers and figures when it finishes.
