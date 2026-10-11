# Why the harnesses differ (SWE-bench, Haiku 5.5)

Behavioural comparison of the six harnesses on the 49 scored SWE-bench Verified tasks
(psf__requests-2317 excluded). Script: `scripts/why_harnesses_differ.py`, output:
`results/swebench/why_harnesses.json`. Final scored row per (task, harness) from
`summary_tokens.csv`; per-run artifacts from `results/swebench/runs/<iid>/<harness>/`.

## What data exists

| harness | step-level transcript | what we can measure |
|---|---|---|
| Cursor | `stdout.txt` stream-json (tool calls, thinking deltas) | every action, thinking volume |
| SWE-agent | `out/*/*.traj` | every action |
| mini-swe-agent | `out/*/*.traj.json` | every action |
| Claude Code | final JSON only (`num_turns`, thinking tokens) | turns, tokens, patch |
| OpenCode | final text + stderr | tokens, patch, how the run ended |
| Aider | console log | tokens, patch, how the run ended |

The proxy logs (`calls.jsonl`) carry sizes and stop reasons, not request bodies, so "did it
run the tests" is only measurable for Cursor, SWE-agent and mini-swe-agent.

Action classification (regex, see script): edit = edit tool / `sed -i` / str_replace_editor /
file writes; test = pytest / runtests.py / unittest; run = ad-hoc python (repro scripts,
`python -c`, heredocs); everything else = read/search.

## Finding 1: wrong fixes are flat; the gap is runs that end with no fix

| harness | fixed | wrong fix | no fix submitted |
|---|---|---|---|
| Cursor | 38 | 11 | **0** |
| SWE-agent | 36 | 12 | 1 |
| Claude Code | 35 | 12 | 2 |
| mini-swe-agent | 34 | 13 | 2 |
| OpenCode | 31 | 13 | 5 |
| Aider | 30 | 13 | **6** |

Every harness submits an incorrect patch on 11-13 tasks. Most of the 8-point gap between
Cursor and Aider is runs that end with an empty patch.

Why runs ended empty:
- **OpenCode:** 7 runs (all failed) ended on "The user rejected permission to use this
  specific tool call": OpenCode's default permission policy asks before some commands
  (e.g. writing repro files outside the project), and headless there is no one to say yes.
  This is a configuration default, not the model; with a permissive config OpenCode would
  likely score higher. We ran every harness on defaults.
- **Aider:** median 2 model calls per task. Aider is built for a human in the loop: it
  proposes edits and asks you to run things. In 22 of 49 runs its last message asks the
  user to run tests or confirm an edit. Headless, nobody answers, so the run ends.
- Claude Code / mini-swe-agent: the 2 empties are long runs that never converged
  (e.g. django-10554, 25 and 44 calls).

## Finding 2: the loop harnesses check their own work

Share of runs that executed code (tests or a repro script) after their first edit:

| harness | ran code after editing | ran the test suite after editing | wrote a repro before editing | median actions | actions before first edit |
|---|---|---|---|---|---|
| SWE-agent | 98% | 98% | 76% | 13 | 4 |
| Cursor | 82% | 82% | 24% | 6 | 2 |
| mini-swe-agent | 63% | 55% | 12% | 6 | 2 |

Across these three, the harness that verifies more often scores higher, but within each
harness verified runs do *not* solve more often (Cursor 75% vs 89% unverified; SWE-agent
73% vs 1/1), because agents test more on harder tasks. So this is a correlation across
three harnesses, not a causal effect. Aider cannot run code in our headless setup at all
(see Finding 1).

## Finding 3: Cursor's edge is small, and partly not the harness

Cursor solved 3 tasks no other harness solved (django-10554, django-14376, sphinx-8638)
and missed none that all others solved.

- **django-14376** is the clearest case. All five other harnesses wrote the same 16-line,
  one-file fix in `mysql/base.py`. Cursor's first command grepped the whole MySQL backend
  for the deprecated keyword, found the second use in `mysql/client.py`, fixed both
  (39 lines, 2 files) and ran the dbshell tests. Looking one step wider won the task.
- **sphinx-8638:** Cursor wrote a 13-line patch in 6 actions; SWE-agent, Claude Code and
  mini wrote 35-48 line patches over 12-40 steps and failed; OpenCode and Aider stopped
  empty (permission prompt / hand-back).
- **django-10554:** Cursor ran for 29 min (the 19-min post-turn hang is in this window)
  and changed 3 files; every other harness failed, 4 of 5 with no patch.

Confounds, stated plainly:
- **Thinking.** Cursor's init line reports the model as "Claude Haiku 5.5 300K High", and
  48 of 49 runs contain thinking events (median ~620 characters per run). The other
  harnesses ran Haiku with little or no thinking (Claude Code median 804 thinking tokens,
  others none). Some of Cursor's edge may be reasoning effort, not harness design.
- **Built-in skills.** Cursor ran with its own built-in skills loaded (account plugins off).
- **Small n.** With 49 tasks the 95% intervals overlap for every pair; 3 unique solves is
  thin evidence.

## Cost (unchanged)

Aider's cost per fix (~8.5c vs 0.55c for OpenCode) comes from re-sending the repo map and
whole files: 4% of its input tokens came from cache vs 90-93% for the others
(cache_read / (input + cache_read + cache_write)).
