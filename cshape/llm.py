import json, os, time, fcntl, threading
from pathlib import Path
import anthropic
from .pricing import MODEL, cost

LEDGER = Path(__file__).resolve().parent.parent / "results" / "ledger.json"
CALLS = LEDGER.parent / "ledger_calls.ndjson"  # .ndjson (not .jsonl) so run-log globs skip it; one line per billed API call, tagged with the run_id of the job that made it
JOB = threading.local()  # run_one sets JOB.run_id / JOB.out so every billed call can be attributed to a logged row
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
    # per-call log (added 4:31 AM CT by the data routine): lets the audit attribute ledger spend to runs, so spend from
    # runs killed mid-flight (no row written) is measured instead of inferred from the ledger-vs-logged gap
    line = dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"), pid=os.getpid(), run_id=getattr(JOB, "run_id", None),
                out=getattr(JOB, "out", None), usd=round(usd, 6), **u)
    with open(CALLS, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(line) + "\n")

def _backoff(sec, kind):
    """Sleep before a retry and account for it on the current job (4:44 AM CT): the org limit is 500k input
    tokens/min shared by all parallel workers, so api_s/wall_s on rows include 429 backoff. notes.backoff_s lets the
    report subtract it; rows written before this change have no backoff fields (treat their latency as unclean)."""
    JOB.backoff_s = getattr(JOB, "backoff_s", 0.0) + sec
    k = f"n_retry_{kind}"
    setattr(JOB, k, getattr(JOB, k, 0) + 1)
    time.sleep(sec)

def reset_job_backoff():
    JOB.backoff_s = 0.0
    for k in ("429", "5xx", "transport"):
        setattr(JOB, f"n_retry_{k}", 0)

def job_backoff():
    return dict(backoff_s=round(getattr(JOB, "backoff_s", 0.0), 1),
                **{f"n_retry_{k}": getattr(JOB, f"n_retry_{k}", 0) for k in ("429", "5xx", "transport")})

_client = None
def call(system, messages, tools=None, max_tokens=16000, run_budget=None):
    """One Messages API call with automatic prompt caching; enforces global hard cap."""
    global _client
    if spent() >= HARD_CAP_USD:
        raise BudgetExceeded(f"hard cap ${HARD_CAP_USD} reached")
    _client = _client or anthropic.Anthropic(max_retries=0, timeout=anthropic.Timeout(300.0, connect=15.0, read=90.0))  # streaming: read=90s is the max gap between chunks, so a hung socket fails in 90s instead of 300s x retries (4:15 AM fix; non-streaming calls through the proxy were hanging 300-1900s)
    kw = dict(model=MODEL, max_tokens=max_tokens, system=system, messages=messages,
              extra_body={"cache_control": {"type": "ephemeral"}})
    if tools:
        kw["tools"] = tools
    t = time.time()
    for attempt in range(12):
        try:
            with _client.messages.stream(**kw) as st:
                r = st.get_final_message()
            break
        except anthropic.APIStatusError as e:
            if e.status_code != 429 and e.status_code < 500:
                raise
            if attempt == 11:
                raise
            _backoff(min(60, 5 * (attempt + 1)), "429" if e.status_code == 429 else "5xx")
        except Exception as e:  # connection drops / read timeouts mid-stream (anthropic or raw httpx errors)
            if isinstance(e, BudgetExceeded) or attempt == 11:
                raise
            _backoff(min(30, 3 * (attempt + 1)), "transport")
    u = dict(input=r.usage.input_tokens or 0, output=r.usage.output_tokens or 0,
             cache_read=getattr(r.usage, "cache_read_input_tokens", 0) or 0,
             cache_write=getattr(r.usage, "cache_creation_input_tokens", 0) or 0)
    usd = cost(u)
    _add(usd, u)
    return r, u, usd, time.time() - t
