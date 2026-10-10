"""Claude Haiku 5.5 list prices, USD per million tokens.
Verified 2026-10-10 from https://docs.anthropic.com/en/docs/about-claude/pricing
Prompts > 100k tokens (input + cache read + cache write) are billed at the higher tier.
"""
MODEL = "claude-haiku-5-5"
TIERS = {
    "le100k": dict(input=0.10, cache_write=0.125, cache_read=0.01, output=0.50),
    "gt100k": dict(input=0.50, cache_write=0.625, cache_read=0.05, output=2.50),
}

def cost(u):
    prompt = u["input"] + u["cache_read"] + u["cache_write"]
    p = TIERS["gt100k" if prompt > 100_000 else "le100k"]
    return sum(u[k] * p[k] for k in p) / 1e6
