"""Every knob for the comparison in one place. Change these before a run, not during it."""
import os
from pathlib import Path

MODEL = "claude-haiku-5-5"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("SBR_OUT", ROOT / "results" / "swebench"))
TOOLS = Path(os.environ.get("SBR_TOOLS", "/opt/sbr-tools"))  # mounted into task containers at the same path

DATASET = "SWE-bench/SWE-bench_Verified"  # the same 500 tasks as princeton-nlp/SWE-bench_Verified, plus the image column the grader needs
SUBSET_SIZE = int(os.environ.get("SBR_SUBSET", "50"))
SUBSET_SEED = 20261010

# The same limits for every harness. The proxy enforces the dollar cap no matter what a harness's own settings say.
TASK_BUDGET_USD = float(os.environ.get("SBR_TASK_BUDGET", "0.50"))
HARD_CAP_USD = float(os.environ.get("SBR_HARD_CAP", "50"))
MAX_TURNS = 50
WALL_S = 30 * 60

IMAGE = "swebench/sweb.eval.x86_64.{key}:latest"  # key = instance_id with "__" -> "_1776_"

def image_for(instance_id):
    return IMAGE.format(key=instance_id.replace("__", "_1776_").lower())
