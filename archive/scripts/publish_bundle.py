"""Build a self-contained publish bundle for bicrick.com: publish/context-shaping/.

Source: docs/BLOG_POST.md (the bicrick.com blog post, with its own YAML front matter) if it exists,
        otherwise docs/CASE_STUDY.md (front matter generated from its title and italic summary).
index.md  = the source with figure links rewritten from ../figures/X.png to figures/X.png
figures/  = copies of every PNG in figures/ (fails loudly if one the text references is missing)

Run after `python -m cshape.article` (it is the last step of `make figures`). $0, no API calls.
"""
import json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "docs" / "BLOG_POST.md"
CASE = ROOT / "docs" / "CASE_STUDY.md"
OUT = ROOT / "publish" / "context-shaping"

if BLOG.exists():
    src = BLOG
    text = BLOG.read_text()
    fm = re.match(r"^---\n.*?\n---\n\n?", text, flags=re.S)
    if not fm:
        sys.exit("publish_bundle: docs/BLOG_POST.md needs YAML front matter")
    front, text = fm.group(0), text[fm.end():]
    text = re.sub(r"^# .+\n\n?", "", text, count=1)                 # title lives in front matter
    if not front.endswith("\n\n"):
        front += "\n"
else:
    src = CASE
    text = CASE.read_text()
    text = re.sub(r"^<!-- GENERATED.*?-->\n", "", text, flags=re.S)
    m = re.search(r"^# (.+)$", text, flags=re.M)
    title = m.group(1).strip()
    text = text[: m.start()] + text[m.end():].lstrip("\n")
    sub = re.search(r"^\*(.+?)\*$", text, flags=re.M)
    summary = sub.group(1).strip() if sub else ""
    front = "---\n" + f"title: {json.dumps(title)}\n" + f"description: {json.dumps(summary)}\n" + \
            "date: 2026-10-10\nauthor: Patrick Brown\ntags: [llm, agents, evals, context-engineering]\n---\n\n"

refs = sorted(set(re.findall(r"\.\./figures/([A-Za-z0-9_\-]+\.png)", text)))
missing = [f for f in refs if not (ROOT / "figures" / f).exists()]
if missing:
    sys.exit(f"publish_bundle: missing figures {missing}")
text = text.replace("../figures/", "figures/")
if "../" in re.sub(r"`[^`]*`", "", text):
    print("publish_bundle: warning, relative ../ links remain outside code spans", file=sys.stderr)

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "figures").mkdir(parents=True)
figs = sorted(p.name for p in (ROOT / "figures").glob("*.png"))
for f in figs:
    shutil.copy2(ROOT / "figures" / f, OUT / "figures" / f)
(OUT / "index.md").write_text(front + text)
print(f"publish/context-shaping: index.md from {src.name} ({len(text.split())} words), {len(figs)} figures ({len(refs)} referenced)")
