# Harness hook registrations

Each hook in `dev_harness/hooks/` runs at the event below.

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
- `block_coined_instrument.py` on `Agent|SendMessage|Write|NotebookEdit`
- `block_alt_grounding.py` on `Agent|SendMessage`
- `block_detour.py` on `Agent|SendMessage|Write|NotebookEdit`
- `block_table_search.py` on `Bash|PowerShell|Grep|Glob`

## PostToolUse

- `archetype_gate.py` on `Write|Edit`

## UserPromptSubmit

- `prompt_router.py` on `(any)`

## Stop

- `session_stop_backstop.py` on `*`
- `block_long_reply.py` on `(any)`
- `block_unanchored_claim.py` on `(any)`

## Not registered

These files sit in the directory and no event runs them.

- `block_missing_skills.py`
