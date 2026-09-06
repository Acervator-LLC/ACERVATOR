# Harness hook registrations

Each hook in `dev_harness/hooks/` runs at the event below.

## PostToolUse

- `archetype_gate.py` on `Write|Edit`

## PreToolUse

- `verify_release_gate.py` on `Write|Edit`
- `archetype_gate.py --pre` on `Write|Edit`
- `block_unanchored_docstring.py` on `Write|Edit`
- `block_heredoc.py` on `Bash|PowerShell`
- `block_heavy_run.py` on `Bash|PowerShell`
- `check_directive_drift.py` on `Agent`
- `block_unreachable_done.py` on `Agent`
- `block_off_item.py` on `Agent|SendMessage`
- `block_new_test.py` on `Write|NotebookEdit`
- `block_narrowed_bar.py` on `Agent|SendMessage`
- `block_subsystem_anchor.py` on `Agent|SendMessage`
- `block_custom_test_run.py` on `Bash|PowerShell`

## Stop

- `session_stop_backstop.py` on `*`
- `block_long_reply.py` on `(any)`

## UserPromptSubmit

- `prompt_router.py` on `(any)`

