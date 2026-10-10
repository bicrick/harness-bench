# OpenAI Codex CLI (open source, Rust)

Code pinned at openai/codex@c3d3b14.

- **Auto-compaction trigger:** `auto_compact_token_limit()` = min(configured limit, 90% of the resolved context window) — https://github.com/openai/codex/blob/c3d3b142d10f4316b46e35aad7e5317e7e506cb7/codex-rs/protocol/src/openai_models.rs#L529-L540. Default `effective_context_window_percent: 95` — https://github.com/openai/codex/blob/c3d3b142d10f4316b46e35aad7e5317e7e506cb7/codex-rs/models-manager/src/model_info.rs#L132.
- **Compaction prompt:** "You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM..." covering progress/decisions, constraints, next steps, critical references — https://github.com/openai/codex/blob/c3d3b142d10f4316b46e35aad7e5317e7e506cb7/codex-rs/prompts/templates/compact/prompt.md. Recent user messages kept up to `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000` — https://github.com/openai/codex/blob/c3d3b142d10f4316b46e35aad7e5317e7e506cb7/codex-rs/core/src/compact.rs#L63.
- **Tool output caps:** shell exec output capped at `DEFAULT_OUTPUT_BYTES_CAP` = 1 MiB — https://github.com/openai/codex/blob/c3d3b142d10f4316b46e35aad7e5317e7e506cb7/codex-rs/utils/pty/src/lib.rs#L25, https://github.com/openai/codex/blob/c3d3b142d10f4316b46e35aad7e5317e7e506cb7/codex-rs/core/src/exec.rs#L81; token-based truncation policies elsewhere (`truncate_text(..., TruncationPolicy::Tokens(..))`, session_prefix.rs).
- **No codebase index:** search is via shell (rg etc.). (Observed from source layout; we found no embedding index. Mark: moderately confident.)
- **Relevance:** a clean, readable reference for "summarize-at-90%" compaction with a handoff-style prompt.
