# Real-world harness panel (arm E)

Every harness runs **headless on claude-haiku-5-5** against our refactor tasks. Each one is pointed at a local logging proxy (`cshape/proxy.py`, which sets `ANTHROPIC_BASE_URL`). The proxy forwards to api.anthropic.com and records the token usage of every request, so all panel members are costed with the same price table. It blocks any other model and stops all traffic at the $50 hard cap. Grading is identical to the other arms.

Licenses and stars come from the GitHub API (`gh api repos/<repo>`) on 2026-10-10. Versions are what we installed.

| Harness | License | Stars | Headless mode | Anthropic key + Haiku 5.5 | How it builds context | Install effort | In panel? |
|---|---|---|---|---|---|---|---|
| Claude Code 2.1.296 | **proprietary** (anthropics/claude-code has no SPDX license) | 149.9k | `claude -p ... --output-format json` | yes (`--model`, `ANTHROPIC_BASE_URL`) | agentic grep/glob/read + CLAUDE.md, compaction, subagents (see research/claude-code.md) | `npm i @anthropic-ai/claude-code` | **yes (closed reference)** |
| OpenCode 1.18.35 (anomalyco/opencode, formerly sst/opencode) | MIT | 212.4k | `opencode run "..." -m anthropic/<model>` | yes (provider `baseURL` set via `OPENCODE_CONFIG_CONTENT`) | agentic tools (read/grep/glob/edit/bash) | `npm i opencode-ai` | **yes** |
| Aider 0.86.2 | Apache-2.0 | 49.4k | `aider --message ... --yes-always` | yes via litellm (`anthropic/<model>`). It needed a model-settings file with `use_temperature: false`, because Haiku 5.5 rejects `temperature` | tree-sitter repo map + PageRank, files added to chat, SEARCH/REPLACE edits | `uv pip install aider-chat` (Python 3.12; pip on 3.13 failed to build a dependency) | **yes** |
| mini-swe-agent 2.4.6 | MIT | 8.4k | `mini -t ... -y --exit-immediately` | yes via litellm | bash-only agent with a linear history and no special tools | `uv pip install mini-swe-agent` | **yes** |
| OpenHands | MIT | 90.4k | headless CLI/SDK exists | yes (litellm) | event stream + LLM summarizing condenser | heavy (Docker sandbox by default; no Docker on box) | no: needs Docker |
| SWE-agent | MIT | 20.5k | `sweagent run` | yes (litellm) | ACI windowed viewer, history processors | needs a Docker/SWE-ReX runtime | no: needs Docker; mini-swe-agent stands in |
| Codex CLI | Apache-2.0 | 128.4k | `codex exec` | OpenAI Responses API first; Anthropic is not native | shell + compaction at 90% | npm | no: would need an OpenAI-compatible shim, which changes the harness |
| Gemini CLI | Apache-2.0 | 107.3k | `gemini -p` | Gemini API only | tools + compression at 50% | npm | no: no Anthropic provider |
| Cline (CLI/SDK) | Apache-2.0 | 70.1k | Cline CLI (SDK restructure in progress) | yes (Anthropic provider) | follows imports, no index | npm; CLI auth flow is interactive | no: not set up in time |
| Goose | Apache-2.0 | 55.1k | `goose run -t` | yes (Anthropic provider) | MCP extensions/tools | binary download plus provider config | no: time; candidate for later |
| Continue CLI | Apache-2.0 | 36.2k | `cn -p` | yes | context providers, repo map tool | npm | no: time |
| Plandex | MIT | 15.7k | server + CLI | yes | project map, plans | server setup; last push 2025-10-03 | no |

## Fairness notes
- Every panel member gets the same instruction text plus the exact test command. Each runs out of the box, with only the settings needed to make Haiku 5.5 work.
- Aider runs in single-message mode (`--message`) without `--auto-test`, which is its default non-interactive behavior. It only edits files it adds to the chat.
- Turn and step caps: Claude Code `--max-turns 40`; mini-swe-agent has no cost limit (`-l 0`), and our global cap applies instead. Wall-time timeout is 900s.
- The proxy counts *model requests*, not tool calls, for the external harnesses (`notes.tool_calls` = number of API calls).
- Single seed per (task, harness) because of time.
