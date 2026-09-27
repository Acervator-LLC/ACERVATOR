# Harness hook registrations

Each hook in `dev_harness/hooks/` runs at the event below.

## PreToolUse

- `verify_release_gate.py` on `Write|Edit`
- `archetype_gate.py --pre` on `Write|Edit`
- `block_unanchored_docstring.py` on `Write|Edit`
- `block_heredoc.py` on `Bash|PowerShell`
- `block_heavy_run.py` on `Bash|PowerShell`
- `check_directive_drift.py` on `Agent`
- `block_uncanonized_workflow.py` on `Agent` — refuses a commissioning brief that
  omits the six questions, a reading shown to fail, the merge gate command, or a
  bare skill line. A brief that is not commissioning exits 0.
- `block_unreachable_done.py` on `Agent`
- `block_off_item.py` on `Agent|SendMessage`
- `block_new_test.py` on `Write|NotebookEdit`
- `block_narrowed_bar.py` on `Agent|SendMessage`
- `block_subsystem_anchor.py` on `Agent|SendMessage`
- `block_custom_test_run.py` on `Bash|PowerShell`
- `block_coined_instrument.py` on `Agent|SendMessage|Write|NotebookEdit` —
  `speakable` drops fenced blocks and lines beginning with `>` before matching,
  so a brief that quotes the banned words passes and the same words as a
  proposal still exit 2.
- `block_alt_grounding.py` on `Agent|SendMessage`
- `block_detour.py` on `Agent|SendMessage|Write|NotebookEdit`
- `block_table_search.py` on `Bash|PowerShell|Grep|Glob`
- `block_missing_skills.py` on `Agent`

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

- `block_delegated_canon.py` — copied to `~/.claude/hooks/`, controls two-sided
  over 11 payloads, 0 wrong. Refuses a `Workflow` script whose `agent(...)` call
  carries a canon run in its arguments, including a name built by `+` or by a
  template slot. A script that authors, one that runs the canon itself through
  `bash(...)`, one that only quotes a canon command, and one that names an
  archetype without instructing a run all exit 0. Over the 195 workflow scripts
  on disk, 132 carry a canon run inside an agent call and 63 do not.
- `block_deflection.py` — copied to `~/.claude/hooks/`, controls two-sided (a
  deflection exits 2, the same words behind `>` exit 0).
- `block_banned_words.py` — copied to `~/.claude/hooks/`, controls two-sided
  over 9 cases, 0 wrong. Refuses the vocabulary the operator banned on
  2026-09-07 in a reply and in an `Agent` or `SendMessage` brief.
  `block_coined_instrument.py` refuses only such a thing being made, so the
  words still reached him inside ordinary prose.
- `block_conversion_table_grounding.py` — refuses an `Agent` or `SendMessage`
  brief that grounds a unit to the conversion table. Driven two-sided: a brief
  naming the table exits 2, a brief naming its own issue exits 0.
- `block_stand_in_without_source.py` — refuses an `Agent` or `SendMessage` brief
  that stands in for an outside source without a `### Real conditions` section
  carrying a figure, and refuses a brief that reads an empty end state as a pass.
  Driven two-sided: the bare brief exits 2, the brief with the section exits 0.
- `block_screen_point_input.py` — refuses a `Write`, `Edit` or `NotebookEdit` of
  a script file that posts input at a screen point or reads the window under a
  point. Driven two-sided: the screen-point script exits 2, a window-handle
  script exits 0, and the hook's own path exits 0.

Each needs an entry in `settings.json`, and the auto-mode classifier refuses the
edit that adds one. Until it is added, none of the six fires.

`block_deflection.py` and `block_banned_words.py` go under `Stop`:

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

`block_delegated_canon.py` goes under `PreToolUse`, matching `Workflow`:

```json
{
  "matcher": "Workflow",
  "hooks": [
    {
      "type": "command",
      "command": "python <home>/.claude/hooks/block_delegated_canon.py",
      "timeout": 15
    }
  ]
}
```
