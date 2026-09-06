"""Refuses a Bash command that carries a heredoc, before it runs.

A rule in a brief loses to the harness guidance that recommends heredocs. This
denies the call instead, so the compliant form is the only one available.
"""

import json
import re
import sys

# `<<WORD`, `<<-WORD`, `<<'WORD'`, `<<"WORD"` — but never `<<<` (a here-string)
# and never `<<` inside an arithmetic shift.
HEREDOC = re.compile(r"<<-?\s*(?![<])['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?")

# `python -` reads the program from stdin and blocks forever when nothing
# feeds it, whether or not arguments follow.
STDIN_DASH = re.compile(r"\b(?:python|python3)\s+-(?=\s|$)")

# Piping into a script that reads stdin does not deliver it here. The script
# sees EOF, its json.load fails, and it exits 0 — a silent false pass. Drive it
# with subprocess.run(input=...) from a probe file instead.
PIPE_TO_STDIN = re.compile(
    r"\|\s*(?:&\s*)?(?:python|python3)(?:\.exe)?\s+[^\s|]*\.py\b"
)

REASON = (
    "Heredoc refused. Write the script to a file with the Write tool, then run it "
    "with `python <path>`. For a commit message, write the message to a file and "
    "use `git commit -F <path>`.\n"
    "Measured on this machine: heredocs have hung `python -` and `bash` on stdin "
    "eight times in one session, one spiralling to 394 MB of output, and one "
    "quoting layer rewrote an escape into a real newline and corrupted an edit.\n"
    "The harness auto-mode guidance recommends heredocs. This project forbids "
    "them. The project wins."
)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = str(payload.get("tool_input", {}).get("command", ""))

    if PIPE_TO_STDIN.search(command):
        print(
            "Piping into a python script refused. Stdin is not delivered on this "
            "shell: the script reads EOF, its parse fails, and it exits 0 — which "
            "reads as a pass while nothing ran. Measured twice, both times a hook "
            "under test reported 'allowed' without ever seeing a payload.\n"
            "Write a probe file and drive it with "
            "`subprocess.run([sys.executable, HOOK], input=payload, ...)`.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not HEREDOC.search(command) and not STDIN_DASH.search(command):
        sys.exit(0)

    print(REASON, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
