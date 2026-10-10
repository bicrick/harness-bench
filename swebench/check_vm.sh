#!/usr/bin/env bash
# Can this machine run the SWE-bench harness comparison?
# Prints specs, then checks the things the runner needs. Read-only: it
# installs nothing and changes nothing.
set -u
ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[31mno\033[0m    %s\n' "$*"; }

echo "== machine"
echo "  arch   $(uname -m)   kernel $(uname -r)"
echo "  cpus   $(nproc)"
echo "  memory $(free -g | awk '/Mem:/{print $2" GB total, "$7" GB available"}')"
echo "  disk   $(df -h "${HOME}" | awk 'NR==2{print $4" free of "$2" at "$6}')"
[ -r /etc/os-release ] && echo "  os     $(. /etc/os-release; echo "$PRETTY_NAME")"

echo "== requirements"
[ "$(uname -m)" = "x86_64" ] && ok "x86_64 (SWE-bench images are x86)" || bad "not x86_64: SWE-bench images need emulation"
[ "$(nproc)" -ge 4 ] && ok "$(nproc) cpus" || warn "only $(nproc) cpus"
mem=$(free -g | awk '/Mem:/{print $2}'); [ "$mem" -ge 12 ] && ok "${mem} GB memory" || warn "${mem} GB memory (OpenHands wants ~8 GB per run)"
freeg=$(df -BG "${HOME}" | awk 'NR==2{gsub("G","",$4); print $4}')
if [ "$freeg" -ge 150 ]; then ok "${freeg} GB free disk"
elif [ "$freeg" -ge 60 ]; then warn "${freeg} GB free: fine for a ~50-task subset if images are deleted after each task"
else bad "${freeg} GB free: too little for local images; use the modal backend"; fi

echo "== privileges"
if sudo -n true 2>/dev/null; then ok "passwordless sudo"; else warn "no passwordless sudo (rootless containers only)"; fi
if unshare -r true 2>/dev/null; then ok "user namespaces (rootless containers possible)"; else bad "no user namespaces (rootless containers won't work)"; fi
[ -e /dev/fuse ] && ok "/dev/fuse present (fuse-overlayfs)" || warn "no /dev/fuse"
[ -f /sys/fs/cgroup/cgroup.controllers ] && ok "cgroup v2" || warn "cgroup v1 or no cgroups"

echo "== container engines"
for e in docker podman; do
  if command -v "$e" >/dev/null; then
    if timeout 20 "$e" info >/dev/null 2>&1; then ok "$e installed and running"
    else warn "$e installed but not usable: $(timeout 20 "$e" info 2>&1 | tail -1)"; fi
  else warn "$e not installed"; fi
done
if command -v docker >/dev/null && timeout 120 docker run --rm hello-world >/dev/null 2>&1; then ok "docker can run a container"
elif command -v podman >/dev/null && timeout 120 podman run --rm docker.io/library/hello-world >/dev/null 2>&1; then ok "podman can run a container"
else warn "no engine could run a test container"; fi

echo "== network"
for u in https://registry-1.docker.io/v2/ https://huggingface.co https://api.anthropic.com https://modal.com https://api2.cursor.sh; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$u"); [ "$code" != "000" ] && ok "$u ($code)" || bad "$u unreachable"
done

echo "== tools"
for t in python3 git node npm uv; do command -v "$t" >/dev/null && ok "$t $($t --version 2>&1 | head -1)" || warn "$t missing"; done
for v in ANTHROPIC_API_KEY CURSOR_API_KEY MODAL_TOKEN_ID; do [ -n "${!v:-}" ] && ok "$v set" || warn "$v not set"; done

echo
echo "Verdict: if 'docker can run a container' or 'podman can run a container' is ok, use --backend docker."
echo "Otherwise use --backend modal (needs a Modal account: pip install modal && modal setup)."
