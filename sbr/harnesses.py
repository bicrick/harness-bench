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
import tempfile
import json, os, shlex, subprocess, uuid
from pathlib import Path
from .config import MODEL, TOOLS, MAX_TURNS, WALL_S, DATASET, image_for

DOCKER = shlex.split(os.environ.get("SBR_DOCKER", "docker"))
CURSOR_MODEL = os.environ.get("SBR_CURSOR_MODEL", MODEL)
# Same fixed resources for every task container (agent and grading), so wall time is comparable across harnesses.
CPUS = os.environ.get("SBR_CPUS", "2"); MEM = os.environ.get("SBR_MEM", "4g")
LIMITS = [f"--cpus={CPUS}", f"--memory={MEM}", f"--memory-swap={MEM}"]
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
    r = _sh(DOCKER + ["run", "-d", "--name", cname, "--network", "host", *LIMITS, *_ca_mounts(),
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

def _in_container(inst, name, argv, env, logdir, env_file=False):
    cname = _container(inst, name)
    base_env = {**_net_env(), "HOME": "/tmp/sbr/home", "TERM": "dumb", "NO_COLOR": "1", "CI": "1",
                "PATH": f"{TESTBED_PATH}:{TOOLS}/node/bin:{TOOLS}/npm/bin:{TOOLS}/cursor/bin:/usr/local/bin:/usr/bin:/bin"}
    notes = {}
    try:
        (logdir / "prompt.txt").write_text(prompt(inst))
        _sh(DOCKER + ["cp", str(logdir / "prompt.txt"), f"{cname}:/tmp/sbr/prompt.txt"])
        if env_file:  # keep secrets out of `ps`: docker reads them from a 0600 temp file
            fd, envpath = tempfile.mkstemp(prefix="sbr-env-")
            with os.fdopen(fd, "w") as f:
                f.write("".join(f"{k}={v}\n" for k, v in {**base_env, **env}.items()))
            env_args = ["--env-file", envpath]
        else:
            envpath, env_args = None, _env_args({**base_env, **env})
        cmd = DOCKER + ["exec", "-w", "/testbed"] + env_args + [cname, "bash", "-c", argv]
        try:
            r = _sh(cmd, timeout=WALL_S)
            out, err, rc = r.stdout, r.stderr, r.returncode
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err, rc = "WALL CLOCK TIMEOUT", -9
            notes["timeout"] = True
        if envpath:
            os.unlink(envpath)
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

def opencode(inst, url, logdir, auto=False):
    cfg = {"$schema": "https://opencode.ai/config.json", "model": f"anthropic/{MODEL}", "small_model": f"anthropic/{MODEL}",
           "provider": {"anthropic": {"options": {"baseURL": url + "/v1"}}},
           "permission": {"edit": "allow", "bash": "allow", "webfetch": "deny"}, "autoupdate": False, "share": "disabled"}
    if auto:  # every permission (incl. external_directory, doom_loop, webfetch) auto-approved: no unattended rejections
        cfg["permission"] = "allow"
    env = {**_anthropic_env(url), "OPENCODE_CONFIG_CONTENT": json.dumps(cfg), "OPENCODE_DISABLE_AUTOUPDATE": "1"}
    return _in_container(inst, "opencode_auto" if auto else "opencode", f'opencode run -m anthropic/{MODEL} "$(cat /tmp/sbr/prompt.txt)"', env, logdir)

CURSOR_CLI_CONFIG = json.dumps({"version": 1, "editor": {"vimMode": False},
                                "permissions": {"allow": [], "deny": []}, "approvalMode": "unrestricted",
                                "sandbox": {"mode": "disabled"}, "notifications": False, "hints": False,
                                "attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}})

def cursor(inst, url, logdir, model=None):
    """Cursor's agent goes to Cursor's servers, not our proxy: no per-call logs, no dollar cap.
    Its cost comes from Cursor's own usage numbers and is reported separately.

    Clean local headless run: a brand-new empty HOME/config dir per run (only a minimal cli-config,
    no auth file, no plugins/marketplaces/MCP/user rules/skills), auth via CURSOR_API_KEY passed in an
    env-file, tools run locally in the task container (no cloud agent, worker, worktree, or resume),
    no --approve-mcps."""
    env = {"CURSOR_API_KEY": os.environ["CURSOR_API_KEY"], "NO_OPEN_BROWSER": "1"}
    setup = ('export HOME=$(mktemp -d /tmp/sbr/cursorhome.XXXXXX) && export CURSOR_CONFIG_DIR=$HOME/.cursor '
             '&& export XDG_CONFIG_HOME=$HOME/.config XDG_CACHE_HOME=$HOME/.cache XDG_DATA_HOME=$HOME/.local/share '
             f'&& mkdir -p $CURSOR_CONFIG_DIR && printf %s {shlex.quote(CURSOR_CLI_CONFIG)} > $CURSOR_CONFIG_DIR/cli-config.json '
             # The account's installed plugins (with their MCP servers, skills, hooks) are git-cloned at startup.
             # There is no CLI flag to skip them, so point every remote git URL at a nonexistent local path:
             # the clones fail instantly and the CLI drops those plugins. /testbed needs no remote.
             '&& git config --global --add safe.directory /testbed && git config --global user.email sbr@example.com '
             '&& git config --global user.name sbr '
             + "".join(f'&& git config --global --add url.file:///nonexistent/.insteadOf {shlex.quote(u)} '
                       for u in ["https://", "http://", "git@", "ssh://", "git://"]) + '&& ')
    argv = setup + (f'agent -p --force --trust --sandbox disabled --workspace /testbed '
                    f'--model {shlex.quote(model or CURSOR_MODEL)} --output-format stream-json "$(cat /tmp/sbr/prompt.txt)"')
    return _in_container(inst, "cursor_nothink" if model else "cursor", argv, env, logdir, env_file=True)

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
    # Variants that remove two confounds (2026-10-11): OpenCode's unattended permission rejections, and Cursor's
    # default Haiku 5.5 id resolving to the thinking/High variant. Same code path otherwise.
    "opencode_auto": lambda inst, url, logdir: opencode(inst, url, logdir, auto=True),
    "cursor_nothink": lambda inst, url, logdir: cursor(inst, url, logdir, model=CURSOR_NOTHINK_MODEL),
}
# Same-settings set (2026-10-11): Haiku 5.5 thinks adaptively by default, so every proxied harness had thinking on.
# These rerun each proxied harness unchanged except that its proxy forces thinking off (proxy.normalize), matching
# cursor_nothink. OpenCode uses the auto-approve config. run.py turns normalization on for any *_nothink name.
for _h in ("mini_swe_agent", "swe_agent", "aider", "claude_code"):
    HARNESSES[f"{_h}_nothink"] = HARNESSES[_h]
HARNESSES["opencode_nothink"] = HARNESSES["opencode_auto"]
CURSOR_NOTHINK_MODEL = os.environ.get("SBR_CURSOR_NOTHINK_MODEL", "claude-haiku-5-5-high")  # "Haiku 5.5 High No Thinking"
PROXIED = set(HARNESSES) - {"cursor", "cursor_nothink", "gold"}
CHECKS = {"gold", "opencode_auto", "cursor_nothink", "mini_swe_agent_nothink", "swe_agent_nothink", "aider_nothink",
          "claude_code_nothink", "opencode_nothink"}  # not run unless asked for by name
