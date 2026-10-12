"""Arm E: real open-source (and one closed) harnesses run headless on Haiku 5.5 through the logging proxy."""
import json, os, shutil, subprocess, tempfile, time
from pathlib import Path
from . import proxy
from .pricing import MODEL, cost

H = Path("/workspace/harnesses")
VENV_BIN = "/workspace/.venv/bin"
TIMEOUT = 900

def _test_cmd(task):
    pp = task["repo"].get("pythonpath", ".")
    args = " ".join(task["repo"].get("pytest_args", ["-c", "/dev/null"]))
    return f"PYTHONPATH={pp} python -m pytest -q -x {args} tests"

def _prompt(task):
    return (f"{task['instruction']}\n\nThis is a refactor in the repository in the current directory. "
            f"Update the definition and every reference (imports, call sites, tests, docstrings/comments, string references). "
            f"Run the tests with: {_test_cmd(task)}\nWork autonomously; do not ask questions.")

def _env(home, url):
    e = {"HOME": str(home), "PATH": f"{VENV_BIN}:/usr/local/bin:/usr/bin:/bin", "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
         "ANTHROPIC_BASE_URL": url, "ANTHROPIC_API_BASE": url, "TERM": "dumb", "NO_COLOR": "1", "CI": "1"}
    return e

def _run(root, task, name, build_cmd):
    srv, rec, url = proxy.start()
    home = Path(tempfile.mkdtemp(prefix=f"home-{name}-"))
    stats = dict(tokens={}, cost_usd=0.0, api_s=0.0, calls=0, notes={"harness": name}, transcript={})
    t0 = time.time()
    try:
        cmd, extra_env = build_cmd(root, task, url, home)
        env = {**_env(home, url), **extra_env}
        try:
            p = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
            out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            out, err, rc = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "TIMEOUT", -9
            stats["notes"]["timeout"] = True
        stats["notes"]["exit_code"] = rc
        stats["transcript"] = {"cmd": cmd, "stdout": out[-50000:], "stderr": err[-20000:], "api_exchanges": rec.bodies}
    finally:
        srv.shutdown(); shutil.rmtree(home, ignore_errors=True)
    for u in rec.calls:
        for k, v in u.items():
            stats["tokens"][k] = stats["tokens"].get(k, 0) + v
        stats["cost_usd"] += cost(u)
    stats["calls"] = len(rec.calls); stats["notes"]["tool_calls"] = len(rec.calls)  # proxy sees model turns, not tool calls
    # upstream 429s (org ITPM limit) seen by the proxy; harnesses retry these with their own backoff and some give up
    stats["notes"]["http_status"] = {str(k): v for k, v in rec.status.items()}
    stats["notes"]["rate_limit_events"] = rec.status.get(429, 0)
    stats["api_s"] = round(time.time() - t0, 1)
    # remove harness droppings that would count as diffs
    for junk in [".aider.chat.history.md", ".aider.input.history", ".aider.tags.cache.v4", ".aider.tags.cache.v3"]:
        p = root / junk
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return stats

def claude_code(root, task):
    def b(root, task, url, home):
        return ([str(H / "npm/node_modules/.bin/claude"), "-p", _prompt(task), "--model", MODEL,
                 "--dangerously-skip-permissions", "--output-format", "json", "--max-turns", "40"],
                {"ANTHROPIC_SMALL_FAST_MODEL": MODEL, "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
                 "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1"})
    return _run(root, task, "claude_code", b)

AIDER_SETTINGS = f"""- name: anthropic/{MODEL}
  edit_format: diff
  weak_model_name: anthropic/{MODEL}
  use_repo_map: true
  use_temperature: false
  examples_as_sys_msg: true
  cache_control: true
  caches_by_default: true
"""

def aider(root, task):
    def b(root, task, url, home):
        (home / "aider-models.yml").write_text(AIDER_SETTINGS)
        return ([str(H / "aider312/bin/aider"), "--model-settings-file", str(home / "aider-models.yml"), "--model", f"anthropic/{MODEL}", "--weak-model", f"anthropic/{MODEL}",
                 "--editor-model", f"anthropic/{MODEL}", "--cache-prompts", "--yes-always", "--no-auto-commits", "--no-dirty-commits",
                 "--no-show-model-warnings", "--no-check-update", "--no-analytics", "--no-pretty", "--no-stream",
                 "--no-gitignore", "--message", _prompt(task)], {})
    return _run(root, task, "aider", b)

def mini_swe_agent(root, task):
    def b(root, task, url, home):
        return ([str(H / "mini312/bin/mini"), "-m", f"anthropic/{MODEL}", "-t", _prompt(task), "-y", "-l", "0",
                 "--exit-immediately", "-o", str(home / "traj.json")],
                {"MSWEA_COST_TRACKING": "ignore_errors", "MSWEA_CONFIGURED": "true", "LITELLM_LOG": "ERROR"})
    return _run(root, task, "mini_swe_agent", b)

def opencode(root, task):
    def b(root, task, url, home):
        cfg = {"$schema": "https://opencode.ai/config.json", "model": f"anthropic/{MODEL}", "small_model": f"anthropic/{MODEL}",
               "provider": {"anthropic": {"options": {"baseURL": url + "/v1"}}},
               "permission": {"edit": "allow", "bash": "allow", "webfetch": "deny"}, "autoupdate": False, "share": "disabled"}
        return ([str(H / "npm/node_modules/.bin/opencode"), "run", "-m", f"anthropic/{MODEL}", _prompt(task)],
                {"OPENCODE_CONFIG_CONTENT": json.dumps(cfg), "OPENCODE_DISABLE_AUTOUPDATE": "1"})
    return _run(root, task, "opencode", b)

EXTERNAL = {"ext_claude_code": claude_code, "ext_aider": aider, "ext_mini_swe_agent": mini_swe_agent, "ext_opencode": opencode}
