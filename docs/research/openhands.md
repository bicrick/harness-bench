# OpenHands (open source)

Condenser code now lives in OpenHands/software-agent-sdk@1cfba21.

- **LLM summarizing condenser:** `max_size=240` events, `keep_first=2` events never condensed; when history exceeds max_size, the middle is summarized and roughly the tail half kept — https://github.com/OpenHands/software-agent-sdk/blob/1cfba2117e92730b0fe1c32520a39aad8611bb8c/openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py#L64-L94. Pipeline and no-op condensers also exist.
- **Evidence:** on a SWE-bench Verified subset, condensation solved 54% vs 53% baseline, with per-turn cost settling to less than half; cost scales linearly instead of quadratically; triggering only at a threshold amortizes prompt-cache rebuilds. — https://www.all-hands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents
- **Caveat:** subset size not given in the post; 1-point difference likely within noise.
