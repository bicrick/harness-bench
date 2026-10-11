# SWE-bench Verified: 6 harnesses x 50 tasks (claude-haiku-5-5)

## Full run (Stage 2, finished 2026-10-11 06:08 CDT)

Every harness ran the whole pinned 50-task subset (`results/swebench/subset.json`) on `claude-haiku-5-5`, graded with the official SWE-bench harness. psf__requests-2317 is excluded for every harness (its grader needs httpbin.org, which is unreachable from the box), so each harness is scored on 49 tasks. Latest good row per pair wins, so the 10 queued old-regime re-runs replace their earlier rows. Generated from `scripts/swebench_tokens.py`, `scripts/swebench_pilot_report.py 50`, `python3 -m sbr.report` and `scripts/swebench_figures.py`.

| harness | solved | pass rate (95% CI) | $ total | $/solve | tokens/task | tokens/solve | median wall s/task* |
|---|---|---|---|---|---|---|---|
| cursor | 38/49 | 78% (64-87%) | 0.421 (est.) | 0.0111 (est.) | 296,691 | 382,575 | 107 |
| swe_agent | 36/49 | 73% (60-84%) | 0.618 | 0.0172 | 312,775 | 425,721 | 226 |
| claude_code | 35/49 | 71% (58-82%) | 0.420 | 0.0120 | 326,016 | 456,423 | 65 |
| mini_swe_agent | 34/49 | 69% (55-80%) | 0.260 | 0.0076 | 136,123 | 196,178 | 74 |
| opencode | 31/49 | 63% (49-75%) | 0.170 | 0.0055 | 94,481 | 149,341 | 57 |
| aider | 30/49 | 61% (47-74%) | 2.560 | 0.0853 | 162,674 | 265,701 | 87 |

\* Wall time uses only rows run under the controlled regime (`concurrency_regime="slots3_cpus2_mem4g"`: 3 agent runs box-wide, 2 CPU / 4 GB per container), 169 of 294 scored rows. $ total counts the final scored row per pair; total proxied API spend across both stages, including retries and preflight, is about $5.34 against the $45 cap (Cursor not included, since it bills through Cursor).

![pass rate](../figures/swebench_pass_rate.png)
![cost vs pass rate](../figures/swebench_cost_vs_pass.png)
![tokens per solve](../figures/swebench_tokens_per_solve.png)

### What the full run says

- The harness moves the score by 17 points on the same model: Cursor 78%, then SWE-agent 73%, Claude Code 71%, mini-SWE-agent 69%, OpenCode 63%, Aider 61%. The confidence intervals still overlap at n=49, so only the ends of the ranking (Cursor vs. Aider/OpenCode) are a real gap.
- Cost spreads far more than accuracy. Aider pays about $0.085 per solve, roughly 15x OpenCode ($0.0055) and 11x mini-SWE-agent ($0.0076), and solves fewer tasks. Its prompts carry repo maps and whole files with a 4% cache hit rate, while the other five sit at 90-93% (cache hit = cache_read / (input + cache_read + cache_write), summed over every call of the final scored row per task; Cursor from its own token logs).
- mini-SWE-agent is the efficiency standout: 69% at about 196k tokens per solve, less than half of what Claude Code (456k) or SWE-agent (426k) spend for 2-4 more solves.
- 26 of 49 tasks were solved by all six harnesses and 8 by none. Unique solves: Cursor 3 (django-10554, django-14376, sphinx-8638), SWE-agent 1 (pytest-10356), Aider 1 (matplotlib-23299).

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

