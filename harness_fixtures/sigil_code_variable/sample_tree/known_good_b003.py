# B003 assignment-to-os-environ: the Use instead block python -m ruff rule B003 prints
import os

os.environ.clear()
os.environ["foo"] = "bar"
