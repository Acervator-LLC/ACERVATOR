# GUI-Quality Calibration

Domain: PySide6 desktop widget code.

## What a GUI-quality peer reviewer looks for

- **Accessibility (WCAG-relevant)**: `setAccessibleName` / `setAccessibleDescription` set on every interactive widget (self plus every child button/input/list); screen-reader-friendly labels ("Submit search" not "Go"); keyboard focus reachability.
- **PySide6 layout conventions**: `QVBoxLayout` / `QHBoxLayout` / `QGridLayout` used instead of `setGeometry` absolute positioning; layouts installed via `setLayout(...)` or QWidget constructor.
- **Widget lifetime**: every child widget passes `self` (or a parent) as the parent argument. Orphan widgets leak or get garbage-collected mid-render.
- **Signal wiring**: every `QPushButton.clicked` / `QLineEdit.returnPressed` / `QAction.triggered` connects to a slot. Buttons with no `.connect(...)` are functionally inert — a bug the AST rule GUI005 catches.
- **Thread discipline**: Qt widgets are main-thread only. Any `QMetaObject.invokeMethod`, `moveToThread`, or `emit` from a worker thread should use `Qt.QueuedConnection`.
- **Docstrings + type hints**: class docstring explains the widget's purpose and any signal it emits; `__init__` typed.
- **Palette / theming**: hardcoded style-sheets are a smell; prefer `QPalette` or a project-wide QSS file. Dark-mode-safe: no hardcoded `#000` / `#FFF`.
- **Semantic labeling**: button text is descriptive ("Save changes" not "OK" for a data-modifying action).

## Severity conventions (peer reviewer)

- **high**: missing accessible name on interactive widget; absolute positioning with `setGeometry` and no layout; hardcoded credential in a widget file.
- **medium**: child widget constructed without parent; missing class docstring; missing signal wiring; hardcoded color literal in a stylesheet.
- **low**: generic button labels ("OK"/"Go"); missing `__init__` docstring; missing return type on `__init__`.

## What the mechanical tools already cover (do not duplicate)

- **gui-static (AST)**: `GUI001` no accessible-name calls, `GUI002` missing class docstring, `GUI003` `setGeometry` without QLayout, `GUI004` interactive child widget without parent argument, `GUI005` interactive widget with no signal wired.
- **ruff** (curated GUI-relevant subset): naming, docstrings, annotations, security via S-family (bandit-mirror).
- **bandit**: security patterns including hardcoded passwords in widget modules.

Peer review adds VALUE for semantic issues: is the button label meaningful? Does the widget compose correctly with the rest of the tab? Would a user with a screen reader understand what pressing this button does?

## What peer review CANNOT reliably do

- Screen-render inspection. Use headless Qt render (`QT_QPA_PLATFORM=offscreen`) + PNG diff for that.
- Accessibility tree inspection. Would need a real Qt test that instantiates the widget.

## Output shape peer reviewer must return

```json
{
  "<filename>": {
    "total_issues": N,
    "issues": [
      {"line": N, "severity": "low|medium|high", "description": "..."}
    ]
  }
}
```

Keep response under 500 words. Do not run tools.
