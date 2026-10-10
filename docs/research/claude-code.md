# Claude Code (closed source; documented behavior)

Sources: Anthropic docs and engineering blog. Not open source, so internals are from docs only.

- **Agentic search, no index.** Claude Code drops `CLAUDE.md` files into context up front and uses glob/grep "to navigate its environment and retrieve files just-in-time, effectively bypassing the issues of stale indexing and complex syntax trees." — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **Compaction.** Message history is passed to the model to summarize "architectural decisions, unresolved bugs, and implementation details while discarding redundant tool outputs"; the agent continues with "this compressed context plus the five most recently accessed files." (same source). Auto-compaction triggers when approaching the context limit; users can steer it with `/compact <instructions>` or a "Compact instructions" section in CLAUDE.md. — https://docs.anthropic.com/en/docs/claude-code/costs
- **Tool-result clearing** is described as "one of the safest lightest touch forms of compaction" (engineering post); `/usage` counts "compaction or tool-result clearing" as expected cache rebuilds (costs doc).
- **Prompt caching** is automatic; cache lifetime is 5 min by default on API keys (1h on subscriptions per the docs); compaction itself is a large request because it reads the whole conversation. — costs doc
- **Deferred tool definitions:** MCP tool definitions are deferred by default; only names enter context until used. — costs doc
- **Subagents for isolation:** docs recommend delegating verbose work (tests, logs, docs fetching) to subagents "so the verbose output stays in the subagent's context while only a summary returns". Anthropic reports subagents typically return a condensed 1,000–2,000 token summary. — costs doc; engineering post
- **Code intelligence plugins** (LSP go-to-definition) are recommended to replace grep + multi-file reads. — costs doc
- **Uncertain:** exact auto-compact threshold percentage is not stated in the docs we read; do not quote a number without a source.
