# Why did SWE-agent do better? (same-settings run, Haiku 5.5, thinking off)

Scope: latest non-excluded row per task for claude_code / cursor / opencode / swe_agent / mini_swe_agent `_nothink`
(cursor_nothink2 ignored). Scores: SWE-agent 37/50, Cursor 35, OpenCode 35, mini-swe-agent 34, Claude Code 33.
Extractor: `scripts/why_swe_agent_extract.py` (heuristic; see caveats).

## The 9 split bugs (order: CC, Cursor, OpenCode, SWE-agent, mini; X = fixed)

| bug | CC Cu OC SW mi | what happened |
|---|---|---|
| astropy-14369 | . X . . . | SWE-agent's one miss: 4 edit-test cycles, still wrong unit grammar. Only Cursor got it. |
| django-13297 | . X X X . | SWE-agent ran the suite after its first fix, saw `FAIL: test_template_params_warning`, rewrote it, got `OK`. Claude Code ended with an empty patch ("I did not ship a fix"). mini made one edit, one test, stopped. |
| django-13315 | X . X X X | Cursor: one edit, one quick run, no suite, partial fix. |
| django-15916 | X . X X X | Cursor: one edit; its test run showed failures it didn't act on. |
| django-16454 | X X X X . | mini reproduced and edited once, stopped; partial fix. |
| matplotlib-25960 | . X X X X | SWE-agent: 4 edit-test cycles, 3 failed checks, revised. Claude Code claimed suite passing but wrong fix. |
| pytest-6197 | . X X X X | SWE-agent: 10 edit-test cycles, 16 failing checks before passing. Claude Code gave up at 49 turns with an empty patch: "I've been stuck in a loop... I'm going to stop here rather than keep guessing." |
| sphinx-8638 | . . . X . | Only SWE-agent. All three other harnesses with tool logs (and CC) patched `find_obj` in the same wrong place. SWE-agent built a tiny Sphinx repro, applied a similar fix, rebuilt, saw the link still pointed at `#pkg.limit`, ran `git checkout` to throw it away, and found the real cause (`rolename='obj'` on the variable field). Others stopped after one fix that "looked right" (CC: "verified only by reading and the existing tests"). |
| sympy-13031 | X X . X X | OpenCode ended with an empty patch after 5 edits / 4 failed checks. |

Pattern: SWE-agent's wins on split bugs come from **running something after the edit, seeing it fail, and revising**
(13297, 25960, 6197, 8638). The other harnesses' losses are mostly **one-shot fixes not re-checked** (Cursor 13315/15916,
mini 13297/16454, everyone on 8638) or **giving up with no patch** (CC twice, OpenCode once).
Not a location-finding story: SWE-agent here used plain bash grep/sed for search, same as others.

## Across all 50 (heuristic, from tool calls)

| harness | checks after first edit | reproduces before editing | revises after a failed check | mean edit→test cycles | median steps | empty patches |
|---|---|---|---|---|---|---|
| SWE-agent | **98%** | 20% | **30%** | **1.6** | 11 | 0 |
| Cursor* | 78% | 12% | 14% | 1.0 | 5 | 0 |
| OpenCode | 76% | 14% | 14% | 1.0 | 7 | 1 |
| mini-swe-agent | 64% | 12% | 10% | 0.9 | 7 | 0 |
| Claude Code** | n/a | n/a | n/a | n/a | 8.5 turns | 2 |

\* Cursor stream-json is capped at 200 KB and lost its beginning in 25/50 runs, so its counts undercount.
\** Claude Code saved only its final summary, no tool trace.

- **Edit linter rejections: ~0.** SWE-agent's config uses `edit_anthropic` with no lint step; its only rejected edit
  in 50 runs was a non-unique `str_replace`. The linter is not the explanation.
- **Submit review:** SWE-agent's review-on-submit fired in 49 runs; it did extra checks after it in 6 and edited after it in 0. Not the explanation.
- **Reproduce-first** is only slightly higher (20% vs 12-14%). Weak signal.
- More cycles also correlates with *hard* bugs (every harness averages more cycles on bugs it failed), so cycles alone are not proof of skill.

## Conclusion

Best-supported explanation: **SWE-agent nearly always runs code after it edits and keeps going when the check fails.**
Same model, same tools in effect (bash); the difference is the loop its prompt and step structure push for. That
shows up exactly on the borderline bugs: 4 of its 8 split wins are visible catch-and-revise sequences.

Confidence: low-to-moderate. n=9 split bugs, overall gap 2-4 bugs, overlapping intervals; behavior metrics are regex
heuristics and two harnesses' logs are incomplete. Fair to say "consistent with", not "proves".

## Figure idea (honest, layman-friendly)

A per-bug strip for the 9 split bugs: one row per harness, each run drawn as a row of small blocks
(grey = look, blue = edit, green/red = check passed/failed), ending in a ✓ or ✗. SWE-agent's rows visibly run longer
with red→blue→green repeats; failing rows tend to be short (one blue, one check, stop). Show Cursor as partial where
truncated and Claude Code as "turns only". Simpler alternative: one bar per harness of "% of runs that checked their fix" (98 vs 64-78).

## Update (Oct 11, late): full-log reruns of Cursor and Claude Code

Cursor and Claude Code were rerun on all 50 bugs with the same settings, saving every step (`cursor_nothink2`: chats
kept and untruncated stream-json; `claude_code_nothink2`: full stream-json with every tool call and result). These
replace their columns in the write-up. Scores: Cursor 36/50 (was 35), Claude Code 34/50 (was 33). The rerun is a
second sample, so a bug or two moving either way is expected noise.

Split bugs with the reruns (6, down from 9; order CC, Cursor, OpenCode, SWE-agent, mini):

| bug | CC Cu OC SW mi |
|---|---|
| astropy-14369 | . X . . . |
| django-13297 | X X X X . |
| django-16454 | X . X X . |
| matplotlib-25960 | . X X X X |
| sphinx-8638 | . . . X . |
| sympy-13031 | . X . X X |

32 bugs every harness fixed, 12 none did. SWE-agent fixed 5 of the 6 splits, Cursor 4, OpenCode 3, CC and mini 2.
sphinx-8638 is still SWE-agent only: both reruns shipped a patch, ran a check, and stopped without revising.

Behavior across all 50, with full logs for every harness (`scripts/why_swe_agent_extract.py`):

| harness | ran code after first edit (all runs) | revises after a failed check | reproduces before editing | mean edit→test cycles | median steps |
|---|---|---|---|---|---|
| SWE-agent | 98% | **30%** | 20% | **1.6** | 11 |
| Cursor (rerun) | 98% | 18% | 28% | 1.4 | 9 |
| Claude Code (rerun) | 96% | 16% | 22% | 1.4 | 8 |
| OpenCode | 76% | 15% | 15% | 1.0 | 7 |
| mini-swe-agent | 64% | 10% | 12% | 0.9 | 7 |

Revised conclusion: with complete logs, "checks its work" no longer separates SWE-agent. Cursor and Claude Code check
almost as often; the earlier 78% for Cursor was an artifact of truncated logs. What still separates SWE-agent is
**going back after a failed check** (30% vs 10–18%) and more edit→test cycles. Confidence stays low: the gap is 1–3
bugs on 6 split bugs.
