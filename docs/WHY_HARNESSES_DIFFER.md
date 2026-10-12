# Why the harnesses differ (SWE-bench, Haiku 5.5)

Behavioural comparison of the six harnesses on the 50-task SWE-bench Verified subset
(psf__requests-2317 replaced by psf__requests-1142), plus two confound-free variants:
`opencode_auto` (all permissions auto-approved) and `cursor_nothink` (Cursor's "Haiku 5.5 High
No Thinking" model id). Script: `scripts/why_harnesses_differ.py`, output:
`results/swebench/why_harnesses.json`. Final scored row per (task, harness) from
`summary_tokens.csv`; per-run artifacts from `results/swebench/runs/<iid>/<harness>/`.

## Same settings (headline, 2026-10-11)

All six harnesses on `claude-haiku-5-5` with thinking off and permissions auto-approved
(`*_nothink` rows; see the "Playing field" section of `docs/SWEBENCH_PILOT.md`). This is the
comparison the write-up uses; the sections below it describe the default-settings run.

| harness | fixed | wrong fix | no fix submitted | ran code after editing | ran tests after editing | repro before editing | median actions |
|---|---|---|---|---|---|---|---|
| SWE-agent | 37 | 13 | 0 | 98% | 94% | 56% | 13 |
| Cursor | 35 | 15 | 0 | 80% | 68% | 12% | 5 |
| OpenCode | 35 | 14 | 1 | n/a | n/a | n/a | n/a |
| mini-swe-agent | 34 | 16 | 0 | 64% | 62% | 24% | 7 |
| Claude Code | 33 | 15 | 2 | n/a | n/a | n/a | n/a |
| Aider | 26 | 19 | 5 | n/a | n/a | n/a | n/a |

- With headless configuration fixed for everyone, empty runs mostly disappear (0-2 per
  harness) except Aider (5), which still hands the turn back to a user who is not there.
- Without thinking, wrong fixes are what separate the field (13-16 for the top five, 19 for
  Aider). Aider's median output fell from about 2,900 to 1,050 tokens per task: with no
  reasoning and only ~2 model calls, it commits to a first guess and never checks it.
- SWE-agent still checks its own work most (98% ran code after an edit) and ties its
  default-settings score (37) while using about 40% fewer tokens per fix.
- 24 tasks were fixed by all six and 12 by none. Only-one-harness fixes: Cursor
  astropy-14369, SWE-agent sphinx-8638.
- Cost per fix: Aider $0.134 vs $0.0044 (mini-swe-agent) to $0.0102 (Claude Code); cache
  hits 2% vs 87-95%.

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
| Cursor | 39 | 11 | **0** |
| SWE-agent | 37 | 12 | 1 |
| Claude Code | 36 | 12 | 2 |
| mini-swe-agent | 35 | 13 | 2 |
| OpenCode | 32 | 13 | 5 |
| Aider | 31 | 13 | **6** |
| *OpenCode, auto-approve* | 36 | 14 | **0** |
| *Cursor, no thinking* | 35 | 15 | 0 |

Every harness submits an incorrect patch on 11-15 tasks. In the original run, most of the
gap between the top and bottom was runs that end with an empty patch.

Why runs ended empty:
- **OpenCode:** 7 runs (all failed) ended on "The user rejected permission to use this
  specific tool call": OpenCode's default policy asks before some commands, and headless
  nobody says yes. **Confirmed by the rerun:** with every permission auto-approved,
  permission stops drop 7 -> 0, empty patches 5 -> 0, and OpenCode goes 32 -> 36 solved
  (+5 tasks, -1). OpenCode's original deficit was an unattended-configuration artifact.
- **Aider:** median 2 model calls per task. Aider is built for a human in the loop; in 22
  runs (counted on the original 49) its last message asks the user to run tests or confirm
  an edit. Headless, nobody answers. This is how Aider behaves unattended; no rerun changes it.
- Claude Code / mini-swe-agent: the 2 empties are long runs that never converged
  (e.g. django-10554, 25 and 44 calls).

## Finding 2: the loop harnesses check their own work

Share of runs that executed code (tests or a repro script) after their first edit:

| harness | ran code after editing | ran the test suite after editing | wrote a repro before editing | median actions | actions before first edit |
|---|---|---|---|---|---|
| SWE-agent | 98% | 98% | 76% | 12.5 | 4 |
| Cursor | 82% | 82% | 24% | 6 | 2 |
| Cursor, no thinking | 80% | 68% | 12% | 5 | 2 |
| mini-swe-agent | 64% | 56% | 12% | 6.5 | 2 |

Still a correlation, not a cause: within each harness, verified runs do *not* solve more
often (Cursor 76% verified vs 89% unverified; SWE-agent 73% vs 1/1), because agents test
more on harder tasks. Without thinking, Cursor still checks its work about as often, but
writes fewer repro scripts up front.

## Finding 3: Cursor's edge was mostly the thinking, not the harness

In the original run Cursor solved 3 tasks no other harness solved (django-10554,
django-14376, sphinx-8638). **Without thinking it solved none of the three**, and dropped
from 39 to 35 (78% -> 70%): -6 tasks (django-10554, django-13315, django-14376,
django-15916, sphinx-8548, sphinx-8638), +2 (astropy-14369, matplotlib-25960). Thinking
was confirmed absent in all 50 no-thinking logs (vs 49 of 50 originals).

- **django-14376** was the showcase: all five other harnesses fixed only `mysql/base.py`
  and failed; thinking Cursor grepped the whole MySQL backend and also fixed
  `mysql/client.py`. No-thinking Cursor wrote the same one-file fix as everyone else and
  failed. The "looks wider before editing" behaviour came from the reasoning, not from
  Cursor's tooling.
- Remaining confound: Cursor still runs with its own built-in skills loaded.

## What changed with the confounds removed

On the same footing, the top five sit within 4 points: SWE-agent 74%, Claude Code 72%,
OpenCode-auto 72%, mini-swe-agent 70%, Cursor-no-thinking 70%; Aider 62%. All 95% CIs
overlap at n=50. What survives:
- Unattended harnesses lose most by **ending without a fix** (Aider hand-backs; OpenCode
  before auto-approve). Configure for headless use and that gap closes.
- **Cost** is the robust difference (below).
What does not survive: "Cursor wins because it looks wider" -- that was thinking.

## Cost

Aider's cost per fix (~8.3c vs 0.54c for OpenCode, 0.71c for OpenCode-auto) comes from
re-sending the repo map and whole files: 4% of its input tokens came from cache vs 90-94%
for the others (cache_read / (input + cache_read + cache_write)). Cursor without thinking
is slightly cheaper per fix than with ($0.0093 vs $0.0109, estimated from its own token logs).
