# SWE-agent (open source)

Code pinned at SWE-agent/SWE-agent@3ea751c.

- **Agent-Computer Interface (ACI):** windowed file viewer and search commands designed for LMs instead of raw shell; the paper argues interface design materially changes performance. — https://arxiv.org/abs/2405.15793 ; windowed viewer: https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/tools/windowed/lib/windowed_file.py
- **History processors:** `LastNObservations` elides all but the last n observations ("our most classic history processor, used in the original paper"); docstring notes it's "not always needed anymore" with modern long-context models — https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/history_processors.py#L85-L115. Also `ClosedWindowHistoryProcessor`, `CacheControlHistoryProcessor`.
- **Observation truncation:** `max_observation_length = 100_000` chars with a `<response clipped>` note — https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/agents.py#L69-L79.
- **Relevance:** "observation masking" (dropping old tool outputs) is a cheap compaction baseline we should include.
