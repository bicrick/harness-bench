import json, os, time, fcntl
from pathlib import Path
import anthropic
from .pricing import MODEL, cost

LEDGER = Path(__file__).resolve().parent.parent / "results" / "ledger.json"
HARD_CAP_USD = float(os.environ.get("CSHAPE_HARD_CAP", "50"))

class BudgetExceeded(RuntimeError):
    pass

def spent():
    return json.loads(LEDGER.read_text())["total_usd"] if LEDGER.exists() else 0.0

def _add(usd, u):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0); txt = f.read()
        d = json.loads(txt) if txt else {"total_usd": 0.0, "calls": 0, "tokens": {}}
        d["total_usd"] += usd; d["calls"] += 1
        for k, v in u.items():
            d["tokens"][k] = d["tokens"].get(k, 0) + v
        f.seek(0); f.truncate(); f.write(json.dumps(d, indent=1))

_client = None
def call(system, messages, tools=None, max_tokens=16000, run_budget=None):
    """One Messages API call with automatic prompt caching; enforces global hard cap."""
    global _client
    if spent() >= HARD_CAP_USD:
        raise BudgetExceeded(f"hard cap ${HARD_CAP_USD} reached")
    _client = _client or anthropic.Anthropic(max_retries=4)
    kw = dict(model=MODEL, max_tokens=max_tokens, system=system, messages=messages,
              extra_body={"cache_control": {"type": "ephemeral"}})
    if tools:
        kw["tools"] = tools
    t = time.time()
    for attempt in range(12):
        try:
            r = _client.messages.create(**kw)
            break
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            if attempt == 11:
                raise
            time.sleep(min(60, 5 * (attempt + 1)))
    u = dict(input=r.usage.input_tokens or 0, output=r.usage.output_tokens or 0,
             cache_read=getattr(r.usage, "cache_read_input_tokens", 0) or 0,
             cache_write=getattr(r.usage, "cache_creation_input_tokens", 0) or 0)
    usd = cost(u)
    _add(usd, u)
    return r, u, usd, time.time() - t
