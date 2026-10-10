"""Build a self-contained publish bundle for bicrick.com: publish/context-shaping/.

index.md  = docs/CASE_STUDY.md with the generator comment stripped, YAML front matter added,
            and figure links rewritten from ../figures/X.png to ./figures/X.png
figures/  = copies of every PNG the article references (fails loudly if one is missing)

Run after `python -m cshape.article` (it is the last step of `make figures`). $0, no API calls.
"""
import json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "CASE_STUDY.md"
OUT = ROOT / "publish" / "context-shaping"

text = SRC.read_text()
text = re.sub(r"^<!-- GENERATED.*?-->\n", "", text, flags=re.S)
m = re.search(r"^# (.+)$", text, flags=re.M)
title = m.group(1).strip()
text = text[: m.start()] + text[m.end():].lstrip("\n")          # title moves to front matter
sub = re.search(r"^\*(.+?)\*$", text, flags=re.M)
summary = sub.group(1).strip() if sub else ""

figs = sorted(set(re.findall(r"\.\./figures/([A-Za-z0-9_\-]+\.png)", text)))
missing = [f for f in figs if not (ROOT / "figures" / f).exists()]
if missing:
    sys.exit(f"publish_bundle: missing figures {missing}")
text = text.replace("../figures/", "./figures/")
if "../" in re.sub(r"`[^`]*`", "", text):
    print("publish_bundle: warning, relative ../ links remain outside code spans", file=sys.stderr)

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "figures").mkdir(parents=True)
for f in figs:
    shutil.copy2(ROOT / "figures" / f, OUT / "figures" / f)
front = "---\n" + f"title: {json.dumps(title)}\n" + f"description: {json.dumps(summary)}\n" + \
        "date: 2026-10-10\nauthor: Patrick Brown\ntags: [llm, agents, evals, context-engineering]\n---\n\n"
(OUT / "index.md").write_text(front + text)
print(f"publish/context-shaping: index.md ({len(text.split())} words), {len(figs)} figures")
