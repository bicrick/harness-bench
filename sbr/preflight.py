"""Check everything the comparison needs before spending real money. Costs well under a cent.

  python -m sbr.preflight
"""
import json, os, shutil, subprocess, sys
from .config import MODEL, TOOLS, OUT, TASK_BUDGET_USD, HARD_CAP_USD
from .harnesses import DOCKER, CURSOR_MODEL

def line(ok, msg):
    print(f"  {'ok  ' if ok else 'FAIL'} {msg}")
    return ok

def main():
    good = True
    print("== machine")
    free = shutil.disk_usage("/").free / 1e9
    good &= line(free >= 60, f"{free:.0f} GB free (want 60+; images are deleted after each task)")
    r = subprocess.run(DOCKER + ["info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    good &= line(r.returncode == 0, f"docker engine {r.stdout.strip() or r.stderr.strip()[-120:]}")

    print("== tools bundle at", TOOLS)
    for p in ["node/bin/node", "npm/bin/claude", "npm/bin/opencode", "cursor/bin/agent", "aider/bin/aider",
              "host/bin/mini-extra", "sweagent/bin/sweagent", "host/bin/python"]:
        good &= line((TOOLS / p).exists(), p)

    print("== keys")
    have_a = bool(os.environ.get("ANTHROPIC_API_KEY"))
    good &= line(have_a, "ANTHROPIC_API_KEY set")
    have_c = bool(os.environ.get("CURSOR_API_KEY"))
    line(have_c, "CURSOR_API_KEY set (needed only for the cursor harness)")

    if have_a:
        print("== one tiny call through the proxy")
        from . import proxy
        OUT.mkdir(parents=True, exist_ok=True)
        srv, rec, url = proxy.start(0.01, OUT / "preflight_calls.jsonl")
        try:
            import httpx
            r = httpx.post(url + "/v1/messages", timeout=60, headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": MODEL, "max_tokens": 16, "messages": [{"role": "user", "content": "Say ok."}]})
            ok = r.status_code == 200 and rec.calls
            good &= line(ok, f"{MODEL} via proxy: HTTP {r.status_code}" + (f", logged {rec.calls[0]['prompt']} prompt tokens" if rec.calls else f" {r.text[:150]}"))
        finally:
            srv.shutdown()

    if have_c:
        print("== cursor")
        r = subprocess.run([str(TOOLS / "cursor/bin/agent"), "models"], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "HOME": str(OUT / "cursor-home")})
        names = r.stdout + r.stderr
        found = CURSOR_MODEL in names
        line(found, f"cursor offers '{CURSOR_MODEL}'" + ("" if found else
             " -- not found. Pick the Haiku 5.5 id from the list below and set SBR_CURSOR_MODEL, or drop cursor from the run"))
        if not found:
            print("\n".join("     " + l for l in names.strip().splitlines()[:40]))

    print(f"== limits: ${TASK_BUDGET_USD:.2f} per task per harness, ${HARD_CAP_USD:.0f} hard cap across the run")
    print("\nREADY" if good else "\nNOT READY: fix the FAIL lines above")
    sys.exit(0 if good else 1)

if __name__ == "__main__":
    main()
