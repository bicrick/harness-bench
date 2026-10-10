# Gemini CLI (open source, TypeScript)

Code pinned at google-gemini/gemini-cli@9b6e026.

- **Compression trigger:** `DEFAULT_COMPRESSION_TOKEN_THRESHOLD = 0.5` (50% of the model's limit), overridable by config or remote experiment flag — https://github.com/google-gemini/gemini-cli/blob/9b6e0265d16bbd29ca51e33c9e0c01dc4cec5e83/packages/core/src/context/chatCompressionService.ts#L45, https://github.com/google-gemini/gemini-cli/blob/9b6e0265d16bbd29ca51e33c9e0c01dc4cec5e83/packages/core/src/config/config.ts#L3454-L3469.
- **What is kept:** most recent ~30% of history preserved (`COMPRESSION_PRESERVE_THRESHOLD = 0.3`, L269); older part summarized. Function-response budget `COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET = 50_000` — older large tool outputs beyond budget are truncated (L274, L357-L412).
- **Tool output masking:** separate service with `DEFAULT_TOOL_PROTECTION_THRESHOLD = 50000` and `DEFAULT_MIN_PRUNABLE_TOKENS_THRESHOLD = 30000` — https://github.com/google-gemini/gemini-cli/blob/9b6e0265d16bbd29ca51e33c9e0c01dc4cec5e83/packages/core/src/context/toolOutputMaskingService.ts#L25-L26.
- **Tool output truncation:** `DEFAULT_TRUNCATE_TOOL_OUTPUT_THRESHOLD = 40_000` — https://github.com/google-gemini/gemini-cli/blob/9b6e0265d16bbd29ca51e33c9e0c01dc4cec5e83/packages/core/src/config/config.ts#L483.
- **Relevance:** compacts much earlier (50%) than Codex (90%) — a natural axis for our compaction-threshold ablation.
