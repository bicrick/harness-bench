# SWE-bench Verified: 6 harnesses x 50 tasks (claude-haiku-5-5)

## Full run (Stage 2, finished 2026-10-11 06:08 CDT)

Every harness ran the whole pinned 50-task subset (`results/swebench/subset.json`) on `claude-haiku-5-5`, graded with the official SWE-bench harness. psf__requests-2317 was dropped from the subset because its grader needs httpbin.org, which is unreachable from the box. It was replaced by psf__requests-1142 using the subset's existing same-repo swap rule (`sbr/subset.py` EXCLUDE). The rule first drew 1724, 1766 and 1921, which use the same live-httpbin tests, then 2931, whose gold patch fails in this environment. 1142's gold patch resolves offline in 22 s. The other 49 tasks are unchanged. All six harnesses ran 1142 on 2026-10-11 under the fair regime, so every harness is scored on the full 50. Latest good row per pair wins, so the 10 queued old-regime re-runs replace their earlier rows. Generated from `scripts/swebench_tokens.py`, `scripts/swebench_final.py`, `scripts/swebench_pilot_report.py 50`, `python3 -m sbr.report` and `scripts/swebench_figures.py`.

| harness | solved | pass rate (95% CI) | $ total | $/solve | tokens/task | tokens/solve | min/solve* |
|---|---|---|---|---|---|---|---|
| cursor | 39/50 | 78% (65-87%) | 0.424 (est.) | 0.0109 (est.) | 292,662 | 375,207 | 8.6 |
| swe_agent | 37/50 | 74% (60-84%) | 0.622 | 0.0168 | 307,879 | 416,052 | 14.2 |
| claude_code | 36/50 | 72% (58-83%) | 0.426 | 0.0118 | 323,186 | 448,870 | 7.2 |
| mini_swe_agent | 35/50 | 70% (56-81%) | 0.264 | 0.0075 | 135,000 | 192,858 | 5.8 |
| opencode | 32/50 | 64% (50-76%) | 0.173 | 0.0054 | 93,850 | 146,641 | 5.4 |
| aider | 31/50 | 62% (48-74%) | 2.566 | 0.0828 | 160,499 | 258,870 | 7.0 |

Pass-rate CIs are 95% Wilson intervals. \* Minutes per solve use only rows run under the controlled regime (`concurrency_regime="slots3_cpus2_mem4g"`: 3 agent runs box-wide, 2 CPU / 4 GB per container), 175 of 300 scored rows: their total wall time divided by their solves. $ total counts the final scored row per pair; total proxied API spend across both stages, including retries and preflight, is about $5.36 against the $45 cap (Cursor not included, since it bills through Cursor).

![pass rate](../figures/swebench_pass_rate.png)
![cost vs pass rate](../figures/swebench_cost_vs_pass.png)
![tokens per solve](../figures/swebench_tokens_per_solve.png)

### What the full run says

- The harness moves the score by 16 points on the same model: Cursor 78%, then SWE-agent 74%, Claude Code 72%, mini-SWE-agent 70%, OpenCode 64%, Aider 62%. The confidence intervals still overlap at n=50, so only the ends of the ranking (Cursor vs. Aider/OpenCode) are a real gap.
- Cost spreads far more than accuracy. Aider pays about $0.083 per solve, roughly 15x OpenCode ($0.0054) and 11x mini-SWE-agent ($0.0075), and solves fewer tasks. Its prompts carry repo maps and whole files with a 4% cache hit rate, while the other five sit at 90-93% (cache hit = cache_read / (input + cache_read + cache_write), summed over every call of the final scored row per task; Cursor from its own token logs).
- mini-SWE-agent is the efficiency standout: 70% at about 193k tokens per solve, less than half of what Claude Code (449k) or SWE-agent (416k) spend for 2-4 more solves.
- 27 of 50 tasks were solved by all six harnesses and 8 by none. Unique solves: Cursor 3 (django-10554, django-14376, sphinx-8638), SWE-agent 1 (pytest-10356), Aider 1 (matplotlib-23299).

### Full-run caveats and deviations (full log: `~/sbr-deviations.md` on the box)

- Cursor $ is a lower-bound estimate from its stream-json token counts at Haiku 5.5's lower price tier; it bypasses the cost proxy.
- One Cursor row (scikit-learn-14710) includes about 19 min of a post-turn hang on a background shell loop; treat its wall time (1584 s) as an outlier.
- Slow harnesses (SWE-agent, Cursor) were split into extra runner shards with per-pair locks so idle slots got used; same code, model and container limits.
- Infra fixes during the run: build-cache pruning for disk, one retry for proxied 0-call rows, upstream 4xx rejections counted as harness failures (one Aider task), and a 300 s hard per-call deadline in `sbr/proxy.py` after two hung SWE-agent calls on django-10554.
- `sbr/report.py` was fixed to let a later good row replace an earlier good row, matching the latest-row rule; before the fix it kept the first good row, which ignored the re-run queue.

## Pilot (first 10 tasks)

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

### What the pilot said

- Pass rate is flat: five harnesses solve 8/10 and Cursor solves 9/10. Ten tasks can't separate them, which is what the full 50 is for.
- Cost is not flat. Aider spent about $1.13 on 10 tasks ($0.14/solve), 10-30x everyone else, because it stuffs large repo maps and whole files into the prompt (one seaborn task in Stage 2 peaked at 172k prompt tokens). OpenCode is the cheapest at about $0.004/solve and about 110k tokens per solve, roughly 3-5x leaner than Claude Code, SWE-agent or Cursor for the same pass rate.
- Total pilot API spend was about $1.46 (Cursor excluded, see below).

### Pilot caveats and deviations (full log: `~/sbr-deviations.md` on the box)

- **Cursor cost is an estimate.** The Cursor CLI bills through Cursor, not the proxy, so its rows have usd=0. Tokens come from the CLI's stream-json usage block and $ is estimated at Haiku 5.5's lower price tier (a lower bound). Cursor was re-run with a clean per-run HOME/config so no account plugins, MCP servers, skills or rules load (they had added ~18-38 min of startup per task over a blocked SSH port). One Cursor pilot task (django-10554) still took 29 min.
- **Wall time is not comparable across harnesses in the pilot.** Early pairs ran sequentially under Docker's slow `vfs` driver; later pairs ran in parallel on `fuse-overlayfs` with no CPU/memory limits. SWE-agent's ~6.5 min median mostly reflects that. From Stage 2 on, rows carry `concurrency_regime="slots3_cpus2_mem4g"` (3 agent runs box-wide, 2 CPU / 4 GB per container), and only those rows should be used for wall-time comparisons.
- SWE-agent needed `temperature: 1.0`, `top_p: null` (Haiku 5.5 rejects temperature 0) and a 900 s runtime startup timeout. These are box config changes, not sbr code changes.
- Five known-broken Verified instances (including django-10097) are excluded from the subset (SWE-bench #267). django-10554 replaces django-10097.
- Error and grade-failed rows are retried automatically. Eight old-regime rows that hit HTTP 429s under parallel load are queued for re-runs (`results/swebench/rerun_queue.json`), and the latest row wins.

