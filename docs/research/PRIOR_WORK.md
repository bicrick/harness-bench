# Prior work

Items marked **[verify]** are from memory/abstracts and need a re-read before quoting numbers.

| Work | URL | What it tested | Limits for our question |
|---|---|---|---|
| SWE-bench | https://arxiv.org/abs/2310.06770 | Issue→patch on real repos; "oracle" vs BM25-retrieved file context settings **[verify]** | Bug fixes, mostly 1–2 files; retrieval ablation done with non-agentic early models |
| SWE-agent | https://arxiv.org/abs/2405.15793 | Agent-computer interface design (viewer, search) ablations | Interface ablation, not context-representation ablation |
| Agentless | https://arxiv.org/abs/2407.01489 | Hierarchical localization (files → classes/functions → lines) using compressed "skeleton" file views, then repair **[verify details]** | Skeleton used for localization only; no skeleton-vs-full comparison on refactors |
| Aider repo map | https://aider.chat/2023/10/22/repomap.html | Design of tree-sitter + graph-ranked map | Design writeup, no controlled ablation vs no-map / full repo |
| RepoCoder | https://arxiv.org/abs/2303.12570 | Iterative retrieval+generation for repo-level completion | Line/function completion, not agentic edits |
| RepoBench | https://arxiv.org/abs/2306.03091 | Cross-file retrieval + completion | Completion only |
| CrossCodeEval | https://arxiv.org/abs/2310.11248 | Completion requiring cross-file context; retrieval helps | Completion only |
| LongCodeBench | https://arxiv.org/abs/2505.07897 | Code QA + bug repair at 32K→1M context; e.g. Claude 3.5 Sonnet 29%→3% | Stuffing long context; no selection strategies compared |
| Lost in the Middle | https://arxiv.org/abs/2307.03172 | U-shaped accuracy vs position of relevant info | QA, not code |
| Context Rot (Chroma) | https://research.trychroma.com/context-rot | 18 models degrade with input length; focused (~300 tok) ≫ full (~113k) on LongMemEval | Synthetic/QA, not code |
| The Complexity Trap (JetBrains) | https://arxiv.org/abs/2508.21433 | Observation masking vs LLM summarization in SWE-agent (plus an OpenHands probe); masking halves cost vs the raw agent and matches or slightly beats LLM-Summary's solve rate; summaries also limit cache reuse (verified 8:15 AM Oct 10 from the arXiv abstract and Table 1) | SWE-bench Verified bug fixes; Qwen3-32B, Qwen3-Coder 480B, Gemini 2.5 Flash; not refactors, not Haiku |
| RefactorBench | https://arxiv.org/abs/2503.07832 | Multi-file refactoring benchmark for agents **[verify]** | Benchmark, not a context-strategy study — possible task source |
| OpenHands condenser | https://www.all-hands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents | Summarizing condenser: 54% vs 53%, <½ per-turn cost | One config, subset size unclear |
| Cursor semantic search | https://cursor.com/blog/semsearch | Semantic search on/off: +12.5% avg on Context Bench; bigger effect on ≥1k-file repos | Proprietary eval; retrieval only |
| Anthropic context engineering | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | Principles: just-in-time retrieval, compaction, notes, subagents | No quantitative ablation |
| Cognition multi-agent posts | https://cognition.com/blog/multi-agents-working | Single-threaded writes; read-only subagents; fine-tuned compression model for long tasks | Opinion/experience, no numbers |
| Cline no-index | https://cline.bot/blog/why-cline-doesnt-index-your-codebase-and-why-thats-a-good-thing | Argument against RAG for code | Argument only |

## Gaps / novel angles for us
1. **Multi-file refactor focus.** Nearly all context studies use bug fixing or completion; refactors stress *finding every caller*, so "missed callers" is a new, crisp metric.
2. **Skeleton-granularity ablation.** No public controlled comparison of tree-only vs +imports vs +signatures vs +docstrings vs full bodies. Aider ships a map but never published that ablation.
3. **Same model, harness-only variable.** Hold a cheap model fixed and vary only context shaping — isolates the harness contribution that Cursor/Anthropic discuss qualitatively.
4. **Compaction-strategy ablation on a cheap model:** trigger 50% vs 90% (Gemini vs Codex defaults), LLM summary vs observation masking vs keep-recent-files.
5. **Cost per success with prompt caching accounted**, not just pass rate.
6. **Static vs agentic context**: does a pre-built skeleton reduce exploratory tool calls enough to beat pure grep/read agents on cost?
