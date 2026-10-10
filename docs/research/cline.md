# Cline (open source)

Code pinned at cline/cline@bf71bf7 (repo was restructured into `sdk/` + `apps/`).

- **Deliberately no index / no RAG.** Cline explores like a developer: read a file, follow imports, read callers. Rationale given: chunking breaks code logic, indexes go stale, embeddings add a security surface. Concedes "RAG can save tokens." — https://cline.bot/blog/why-cline-doesnt-index-your-codebase-and-why-thats-a-good-thing
- **Compaction modes exist in the SDK:** event types `auto_compaction`, `manual_compaction`, `compaction_budget_emergency` — https://github.com/cline/cline/blob/bf71bf7cd9fe6816972d7ae5ca5ff0e04e63f87d/sdk/packages/shared/src/agents/types.ts#L192-L194; pluggable compaction examples in `sdk/examples/plugins/custom-compaction.ts`.
- **Uncertain:** exact compaction thresholds in the current SDK not confirmed in this pass.
