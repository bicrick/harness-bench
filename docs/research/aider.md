# Aider (open source)

Code pinned at Aider-AI/aider@5dc9490.

- **Repo map = skeleton.** Each request includes a map of files with key symbols and their definition lines (signatures, not bodies). — https://aider.chat/docs/repomap.html
- **Ranking:** a graph of files (edges = symbol references) ranked with PageRank; only the top parts fitting a token budget are sent. `--map-tokens` defaults to 1k and expands when no files are in chat. — repomap docs; https://aider.chat/2023/10/22/repomap.html
- **Heuristics in code** (https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py#L480-L512): identifiers mentioned in chat ×10; long snake/camel/kebab identifiers (≥8 chars) ×10; private `_x` ×0.1; identifiers defined in >5 files ×0.1; references from files already in chat ×50; reference counts are sqrt-dampened. Personalization vector gives chat files/mentioned files weight (`100/len(fnames)`, ~L383).
- **Map grows when no files added:** `map_mul_no_files=8` (https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L323).
- **Explicit file adds:** full contents of files the user adds are sent; the model can request more files via the map.
- **History summarization:** a background thread summarizes old chat when it exceeds `max_chat_history_tokens` (https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L1002-L1032).
- **Relevance to us:** Aider's repo map is the reference implementation of our "skeleton" strategy; tree-sitter tags + PageRank are directly reusable (Apache-2.0).
