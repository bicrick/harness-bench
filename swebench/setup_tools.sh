#!/usr/bin/env bash
# Build the tools bundle that gets mounted (read-only, at the same path) into every SWE-bench task
# container, so the CLI harnesses run inside the task's real environment:
#   node + Claude Code + OpenCode, Cursor's `agent`, and Aider on a portable Python.
# Also builds the host-side venvs for mini-swe-agent, SWE-agent and the SWE-bench grader.
#
#   SBR_TOOLS=/opt/sbr-tools bash swebench/setup_tools.sh
set -euo pipefail
TOOLS="${SBR_TOOLS:-/opt/sbr-tools}"
NODE_VERSION="${NODE_VERSION:-22.22.0}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$TOOLS" || { echo "cannot create $TOOLS (try SBR_TOOLS=\$HOME/sbr-tools)"; exit 1; }
cd "$TOOLS"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

echo "== node $NODE_VERSION"
if [ ! -x node/bin/node ]; then
  curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" | tar -xJ
  rm -rf node && mv "node-v${NODE_VERSION}-linux-x64" node
fi
export PATH="$TOOLS/node/bin:$PATH"

echo "== Claude Code + OpenCode"
npm install -g --prefix "$TOOLS/npm" --no-fund --no-audit @anthropic-ai/claude-code opencode-ai >/dev/null
"$TOOLS/npm/bin/claude" --version
"$TOOLS/npm/bin/opencode" --version

echo "== Cursor agent"
if [ ! -e "$TOOLS/cursor/bin/agent" ]; then
  mkdir -p "$TOOLS/cursor"
  HOME="$TOOLS/cursor" bash -c 'curl -fsS https://cursor.com/install | bash' >/dev/null
  mkdir -p "$TOOLS/cursor/bin"
  ln -sf "$(readlink -f "$TOOLS/cursor/.local/bin/agent")" "$TOOLS/cursor/bin/agent"
fi
"$TOOLS/cursor/bin/agent" --version || echo "  (cursor agent installed; version check needs network/auth)"

echo "== Aider on a portable Python"
uv python install 3.12 --install-dir "$TOOLS/python" >/dev/null
PY="$(find "$TOOLS/python" -maxdepth 3 -path '*/bin/python3.12' | head -1)"
[ -x "$TOOLS/aider/bin/aider" ] || { uv venv -q --python "$PY" "$TOOLS/aider" && uv pip install -q --python "$TOOLS/aider/bin/python" aider-chat; }
"$TOOLS/aider/bin/aider" --version

echo "== host side: grader, mini-swe-agent, SWE-agent"
uv venv -q --python 3.12 "$TOOLS/host" 2>/dev/null || true
uv pip install -q --python "$TOOLS/host/bin/python" swebench datasets httpx mini-swe-agent
if [ ! -d "$TOOLS/swe-agent-src" ]; then
  git clone -q --depth 1 https://github.com/SWE-agent/SWE-agent.git "$TOOLS/swe-agent-src"
fi
uv venv -q --python 3.12 "$TOOLS/sweagent" 2>/dev/null || true
uv pip install -q --python "$TOOLS/sweagent/bin/python" -e "$TOOLS/swe-agent-src"

du -sh "$TOOLS" | awk '{print "== tools bundle: "$1" at '"$TOOLS"'"}'
echo "Next: python -m sbr.subset, then python -m sbr.run --pilot"
