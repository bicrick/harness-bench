# Pre-registered hypotheses (committed before main runs, Sat Oct 10 2026 ~1:45 AM CT)

The model is Claude Haiku 5.5 throughout. There are 19 multi-file refactor tasks, and the grader requires tests to pass, no leftover references, and the task check to pass. Each hypothesis states its prediction and how it is tested.

- **H1 (layout):** `full` (naive) has a lower pass rate than `touched` (oracle). On marshmallow (>100k tokens) `full` also has the highest cost per solve. *Test:* paired per-task comparison; McNemar on per-(task, seed) pass.
- **H2 (skeleton ladder):** pass rate rises from L0 to L2, and L3 adds little over L2. Missed callers fall as the level rises. *Test:* trend across levels; file-selection recall for each level.
- **H3 (agentic):** agentic strategies (`agentic`, `skel_retrieval`) beat every single-shot strategy except possibly `touched`, because they can run tests and re-grep. `skel_retrieval` uses fewer tool calls than `agentic`.
- **H4 (tool design):** structured tools (find_references/rename) beat raw grep/edit on pass rate and lower missed callers to near zero, at equal or lower cost.
- **H5 (compaction):** under a tight budget, dropping old tool outputs matches or beats LLM summarization at lower cost. Summarizing at 50% is worse than summarizing at 90%.
- **H6 (skills):** a short refactor skill ("find all references, update, run tests, re-grep") improves pass rate more than a generic AGENTS.md conventions doc.
- **H7 (headline):** the best combined harness beats the naive baseline by **≥20 pp** in pass rate at a **lower** cost per solved task.

Any result that contradicts a hypothesis will be reported as such.
