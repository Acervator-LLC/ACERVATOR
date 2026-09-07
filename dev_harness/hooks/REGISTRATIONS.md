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
- `block_deflection.py` — copied to `~/.claude/hooks/`, controls two-sided (a
  deflection exits 2, the same words behind `>` exit 0).
- `block_banned_words.py` — copied to `~/.claude/hooks/`, controls two-sided
  over 9 cases, 0 wrong. Refuses the vocabulary the operator banned on
  2026-09-07 in a reply and in an `Agent` or `SendMessage` brief.
  `block_coined_instrument.py` refuses only such a thing being made, so the
  words still reached him inside ordinary prose.

Both need an entry under `Stop`, and the auto-mode classifier refuses the edit
to `settings.json` that adds one. Until it is added, neither fires.

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "python <home>/.claude/hooks/block_deflection.py",
      "timeout": 15
    }
  ]
}
```
