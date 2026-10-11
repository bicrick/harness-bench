# SWE-bench live dashboard

Read-only status page for the Haiku 5.5 harness runs. Polls `results/swebench/` every 20s and serves HTML on port 8787.

## Setup

```bash
# Secret path token (never commit this)
export SBR_DASH_TOKEN="$(openssl rand -hex 16)"
# or write it to a file and point at it:
# export SBR_DASH_TOKEN_FILE=/path/to/token

# Optional overrides
export SBR_RESULTS="$HOME/context-shaping/results/swebench"   # default
export SBR_HARD_CAP=45

python3 tools/dashboard/dash.py
# → http://127.0.0.1:8787/$SBR_DASH_TOKEN
```

A restart loop is useful in tmux:

```bash
while true; do nice -n 10 python3 tools/dashboard/dash.py; sleep 3; done
```

## Public tunnel (optional)

Either works. Prefer cloudflared if you have it; ngrok is fine too.

```bash
# cloudflared (ephemeral URL; pin a named tunnel if you want a stable host)
cloudflared tunnel --url http://127.0.0.1:8787

# ngrok
ngrok http 8787
```

Share only `https://<tunnel-host>/$SBR_DASH_TOKEN`. Do not commit the token, ngrok auth token, or cloudflared credentials.

## Notes

- Lead table = same-settings set (`*_nothink` + `cursor_nothink`), thinking off.
- Earlier thinking-on / default runs are under a collapsed section.
- Cursor `$` stays 0 (not proxied); tokens come from Cursor's own logs.
