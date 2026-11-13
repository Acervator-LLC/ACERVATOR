# S607 start-process-with-partial-path: the Use instead block python -m ruff rule S607 prints
import subprocess

subprocess.Popen(["/usr/bin/ruff", "check", "file.py"])
