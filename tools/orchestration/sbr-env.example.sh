# Source before launching runners. Copy to sbr-env.sh (gitignored) and fill in.
# Never commit real API keys or tokens.

export SBR_TOOLS=${SBR_TOOLS:-$HOME/sbr-tools}
export SBR_HARD_CAP=${SBR_HARD_CAP:-45}
export SBR_DOCKER=${SBR_DOCKER:-"sudo docker"}
export SBR_RESULTS=${SBR_RESULTS:-$HOME/context-shaping/results/swebench}

# Host python that has the swebench / harness deps
export PY=${PY:-$SBR_TOOLS/host/bin/python}

# Fill these in locally (do not commit):
# export ANTHROPIC_API_KEY=...
# export CURSOR_API_KEY=...
# export OPENAI_API_KEY=...          # if a harness needs it
# export SBR_DASH_TOKEN=...          # dashboard secret path
# export NGROK_AUTHTOKEN=...         # only if using ngrok
