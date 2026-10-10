"""One adapter per harness. Each takes one SWE-bench instance and returns the patch it produced.

Two kinds:
  - in-container CLIs (Claude Code, OpenCode, Cursor, Aider) run inside the task's own container, from the
    read-only tools bundle mounted at TOOLS, so their shell commands see the task's real Python environment.
  - SWE-bench-native agents (mini-swe-agent, SWE-agent) run on the host and drive the same task image
    through their own Docker integration, with their shipped SWE-bench configs.

Every harness gets the same model, the same per-task dollar cap (enforced by the proxy), the same turn
limit where the harness has one, and the same wall clock. Settings are otherwise each harness's defaults.
Cursor is the exception on cost: it talks to Cursor's servers, so the proxy can't see or cap it.
"""
import json, os, shlex, subprocess, uuid
from pathlib import Path
from .config import MODEL, TOOLS, MAX_TURNS, WALL_S, DATASET, image_for

DOCKER = shlex.split(os.environ.get("SBR_DOCKER", "docker"))
CURSOR_MODEL = os.environ.get("SBR_CURSOR_MODEL", MODEL)
TESTBED_PATH = "/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin"
JUNK = [".aider*", ".claude", ".opencode", ".cursor", "*.orig", "*.rej"]

def prompt(inst):
    return (f"<issue>\n{inst['problem_statement'].strip()}\n</issue>\n\n"
            "The repository is checked out at /testbed and its Python environment is already on PATH. "
            "Resolve the issue by editing the repository's source files. Don't add or change tests. "
            "Work autonomously and don't ask questions; stop when the fix is done.")

def _sh(cmd, timeout=None, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)

# ---------- in-container CLIs ----------

def _env_args(env):
    out = []
    for k, v in env.items():
        out += ["-e", f"{k}={v}"]
    return out

# If the host reaches the internet through a proxy, containers need the same settings and CA bundle.
# Unset on a machine with direct internet, so this is a no-op there.
PROXY_VARS = ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"]
CA_VARS = ["SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE"]

def _net_env():
    env = {k: os.environ[k] for k in PROXY_VARS + CA_VARS if os.environ.get(k)}
    if any(k in env for k in PROXY_VARS):  # keep our local logging proxy off the upstream proxy
        no = ",".join(filter(None, [os.environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
        env["NO_PROXY"] = env["no_proxy"] = no
    return env

def _ca_mounts():
    files = {os.environ[k] for k in CA_VARS if os.environ.get(k) and Path(os.environ[k]).is_file()}
    return [a for f in sorted(files) for a in ("-v", f"{f}:{f}:ro")]

def _container(inst, name):
    cname = f"sbr-{name}-{uuid.uuid4().hex[:8]}"
    r = _sh(DOCKER + ["run", "-d", "--name", cname, "--network", "host", *_ca_mounts(),
                      "-v", f"{TOOLS}:{TOOLS}:ro", image_for(inst["instance_id"]), "sleep", "infinity"])
    if r.returncode:
        raise RuntimeError(f"docker run failed: {r.stderr.strip()[-400:]}")
    _sh(DOCKER + ["exec", cname, "bash", "-lc",
                  "mkdir -p /tmp/sbr/home && cd /testbed && git config --global --add safe.directory /testbed "
                  "&& git config --global user.email sbr@example.com && git config --global user.name sbr"])
    return cname

def _patch(cname):
    excl = " ".join(f"':(exclude){j}'" for j in JUNK)
    r = _sh(DOCKER + ["exec", cname, "bash", "-lc", f"cd /testbed && git add -A && git diff --cached --binary HEAD -- . {excl}"])
    return r.stdout

def _in_container(inst, name, argv, env, logdir):
    cname = _container(inst, name)
    base_env = {**_net_env(), "HOME": "/tmp/sbr/home", "TERM": "dumb", "NO_COLOR": "1", "CI": "1",
                "PATH": f"{TESTBED_PATH}:{TOOLS}/node/bin:{TOOLS}/npm/bin:{TOOLS}/cursor/bin:/usr/local/bin:/usr/bin:/bin"}
    notes = {}
    try:
        (logdir / "prompt.txt").write_text(prompt(inst))
        _sh(DOCKER + ["cp", str(logdir / "prompt.txt"), f"{cname}:/tmp/sbr/prompt.txt"])
        cmd = DOCKER + ["exec", "-w", "/testbed"] + _env_args({**base_env, **env}) + [cname, "bash", "-c", argv]
        try:
            r = _sh(cmd, timeout=WALL_S)
            out, err, rc = r.stdout, r.stderr, r.returncode
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err, rc = "WALL CLOCK TIMEOUT", -9
            notes["timeout"] = True
        (logdir / "stdout.txt").write_text(out[-200000:])
        (logdir / "stderr.txt").write_text(err[-50000:])
        notes["exit_code"] = rc
        return _patch(cname), notes
    finally:
        _sh(DOCKER + ["rm", "-f", cname])

def _anthropic_env(url):
    return {"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"], "ANTHROPIC_BASE_URL": url, "ANTHROPIC_API_BASE": url}

def claude_code(inst, url, logdir):
    env = {**_anthropic_env(url), "IS_SANDBOX": "1", "ANTHROPIC_SMALL_FAST_MODEL": MODEL,
           "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
           "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1"}
    argv = (f'claude -p "$(cat /tmp/sbr/prompt.txt)" --model {MODEL} --dangerously-skip-permissions '
            f'--max-turns {MAX_TURNS} --output-format json')
    return _in_container(inst, "claude_code", argv, env, logdir)

def opencode(inst, url, logdir):
    cfg = {"$schema": "https://opencode.ai/config.json", "model": f"anthropic/{MODEL}", "small_model": f"anthropic/{MODEL}",
           "provider": {"anthropic": {"options": {"baseURL": url + "/v1"}}},
           "permission": {"edit": "allow", "bash": "allow", "webfetch": "deny"}, "autoupdate": False, "share": "disabled"}
    env = {**_anthropic_env(url), "OPENCODE_CONFIG_CONTENT": json.dumps(cfg), "OPENCODE_DISABLE_AUTOUPDATE": "1"}
    return _in_container(inst, "opencode", f'opencode run -m anthropic/{MODEL} "$(cat /tmp/sbr/prompt.txt)"', env, logdir)

def cursor(inst, url, logdir):
    """Cursor's agent goes to Cursor's servers, not our proxy: no per-call logs, no dollar cap.
    Its cost comes from Cursor's own usage numbers and is reported separately."""
    env = {"CURSOR_API_KEY": os.environ["CURSOR_API_KEY"]}
    argv = f'agent -p --force --model {shlex.quote(CURSOR_MODEL)} --output-format json "$(cat /tmp/sbr/prompt.txt)"'
    return _in_container(inst, "cursor", argv, env, logdir)

AIDER_SETTINGS = f"""- name: anthropic/{MODEL}
  edit_format: diff
  weak_model_name: anthropic/{MODEL}
  use_repo_map: true
  use_temperature: false
  examples_as_sys_msg: true
  cache_control: true
  caches_by_default: true
"""

def aider(inst, url, logdir):
    """Aider is built for a human in the loop; headless it gets one message and its own auto-fix loop."""
    (logdir / "aider-models.yml").write_text(AIDER_SETTINGS)
    argv = (f"cat > /tmp/sbr/aider-models.yml <<'EOF'\n{AIDER_SETTINGS}EOF\n"
            f'{TOOLS}/aider/bin/aider --model-settings-file /tmp/sbr/aider-models.yml --model anthropic/{MODEL} '
            f'--weak-model anthropic/{MODEL} --editor-model anthropic/{MODEL} --cache-prompts --yes-always '
            '--no-auto-commits --no-dirty-commits --no-show-model-warnings --no-check-update --no-analytics '
            '--no-pretty --no-stream --no-gitignore --message-file /tmp/sbr/prompt.txt')
    return _in_container(inst, "aider", argv, _anthropic_env(url), logdir)

# ---------- SWE-bench-native agents (host side) ----------

def _host(cmd, env, logdir, preds_path, iid):
    full_env = {**os.environ, **env}
    notes = {}
    try:
        r = _sh(cmd, timeout=WALL_S, env=full_env, cwd=logdir)
        out, err, rc = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired as e:
        out, err, rc = "", "WALL CLOCK TIMEOUT", -9
        notes["timeout"] = True
    (logdir / "stdout.txt").write_text((out or "")[-200000:])
    (logdir / "stderr.txt").write_text((err or "")[-50000:])
    notes["exit_code"] = rc
    patch = ""
    if preds_path.exists():
        preds = json.loads(preds_path.read_text())
        if isinstance(preds, dict):
            patch = (preds.get(iid) or {}).get("model_patch") or ""
        else:
            patch = next((p.get("model_patch") or "" for p in preds if p.get("instance_id") == iid), "")
    return patch, notes

def mini_swe_agent(inst, url, logdir):
    iid = inst["instance_id"]
    cmd = [str(TOOLS / "host/bin/mini-extra"), "swebench", "--subset", "verified", "--split", "test",
           "--filter", f"^{iid}$", "-m", f"anthropic/{MODEL}", "-o", str(logdir / "out"), "-w", "1",
           "-c", "swebench.yaml", "-c", f"agent.step_limit={MAX_TURNS}", "-c", "agent.cost_limit=100"]
    env = {**_anthropic_env(url), "MSWEA_COST_TRACKING": "ignore_errors", "MSWEA_CONFIGURED": "true", "LITELLM_LOG": "ERROR"}
    return _host(cmd, env, logdir, logdir / "out" / "preds.json", iid)

def swe_agent(inst, url, logdir):
    iid = inst["instance_id"]
    cmd = [str(TOOLS / "sweagent/bin/sweagent"), "run-batch",
           "--config", str(TOOLS / "swe-agent-src/config/default.yaml"),
           "--agent.model.name", f"anthropic/{MODEL}", "--agent.model.api_base", url,
           "--agent.model.per_instance_cost_limit", "0", "--agent.model.total_cost_limit", "0",
           "--agent.model.per_instance_call_limit", str(MAX_TURNS),
           "--instances.type", "swe_bench", "--instances.subset", "verified", "--instances.split", "test",
           "--instances.filter", f"^{iid}$", "--output_dir", str(logdir / "out"), "--num_workers", "1"]
    return _host(cmd, _anthropic_env(url), logdir, logdir / "out" / "preds.json", iid)

def gold(inst, url, logdir):
    """Smoke test, not a contender: applies SWE-bench's reference fix inside the container. If the plumbing
    (container, patch extraction, grading) is right, every gold run resolves."""
    (logdir / "gold.diff").write_text(inst["patch"])
    cname = _container(inst, "gold")
    try:
        _sh(DOCKER + ["cp", str(logdir / "gold.diff"), f"{cname}:/tmp/sbr/gold.diff"])
        r = _sh(DOCKER + ["exec", "-w", "/testbed", cname, "bash", "-lc", "git apply /tmp/sbr/gold.diff"])
        return _patch(cname), {"exit_code": r.returncode}
    finally:
        _sh(DOCKER + ["rm", "-f", cname])

HARNESSES = {
    "mini_swe_agent": mini_swe_agent,
    "swe_agent": swe_agent,
    "opencode": opencode,
    "aider": aider,
    "claude_code": claude_code,
    "cursor": cursor,
    "gold": gold,
}
PROXIED = set(HARNESSES) - {"cursor", "gold"}
CHECKS = {"gold"}  # not run unless asked for by name
