# Summary: how harnesses shape context

Per-tool details and citations in the sibling files. "?" = not verified this pass.

| Tool | Codebase discovery | Skeleton / repo map | Compaction trigger | What compaction keeps | Tool-output limits | Subagents |
|---|---|---|---|---|---|---|
| Claude Code | agentic grep/glob + CLAUDE.md up front | no (LSP plugins optional) | near context limit (exact % ?) | summary + 5 most recent files; tool-result clearing | hooks recommended to filter | yes, return summaries |
| Cursor | semantic search (custom embeddings) + grep | ? | ? | ? | ? | ? |
| Aider | user-added files + repo map | **yes**, tree-sitter + PageRank, ~1k tokens default | history > max_chat_history_tokens | LLM summary of old chat | n/a | no |
| Codex CLI | shell (rg) | no | min(config, 90% of window) | handoff summary + ≤20k tokens recent user msgs | 1 MiB exec cap + token truncation | ? |
| Gemini CLI | tools (read/grep/glob) | no | **50%** of window | summary + latest 30% | 40k truncate; 50k tool-response budget; masking | yes (agents pkg) |
| Cline | follow imports/callers; no index by design | no | auto / manual / emergency | ? | ? | ? |
| OpenHands | tools | no | >240 events | first 2 events + summary + tail | ? | yes |
| SWE-agent | windowed viewer + search | no | n/a (classic: keep last n observations) | last n observations | 100k chars | no |
| Continue | context providers | yes, on-demand repo map tool | ? | ? | token pruning | ? |

## Patterns
1. **Agentic search is the default**; only Cursor (and Continue optionally) invest in embeddings, and Cursor's own data says grep+semantic beats grep alone, more so on big repos.
2. **Skeletons are rare as an always-on layer** — Aider is the main example. Most tools let the model build its own map through tool calls.
3. **Compaction triggers vary 50%→90%+** of window and keep very different things (recent files, recent N%, first+last events). Nobody publishes an ablation of these choices for coding.
4. **Cheapest compaction is dropping old tool output** (SWE-agent observation masking, Claude tool-result clearing, Gemini masking).
5. **Context length hurts on its own** (Chroma context rot; LongCodeBench) — argues for tighter context, especially for small models.

## Open questions for our experiments
- Does a skeleton beat full repo for a *cheap* model on multi-file refactors, and at what skeleton granularity?
- Does skeleton+retrieval recover what pure skeleton misses (callers)?
- Compaction: 50% vs 90% trigger; LLM summary vs observation masking; keep-recent-files or not.
- Cost per successful task, including cache effects.
