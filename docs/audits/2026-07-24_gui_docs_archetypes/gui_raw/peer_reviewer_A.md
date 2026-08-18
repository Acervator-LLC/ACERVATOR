# GUI Peer Reviewer A — full transcript

Spawned via `Agent(subagent_type="general-purpose")` before session
limit was hit at 19:09 PST. Instructed to review the two GUI
fixtures using judgment only (no tool invocation).

## Response

FILE: known_good_widget.py
  - No issues found. Class docstring present (lines 21-26), QVBoxLayout used, all interactive widgets have setAccessibleName/setAccessibleDescription, child widgets pass `self` as parent, type-annotated `__init__`.

FILE: known_bad_widget.py
  - LINE 20: Hardcoded credential `ADMIN_PASSWORD = "letmein"` at module scope. [SEVERITY: high]
  - LINE 23: `LegacyForm` class missing docstring. [SEVERITY: medium]
  - LINE 25: `__init__` missing type hints on `parent` and return. [SEVERITY: low]
  - LINE 26: `LegacyForm` widget itself never calls `setAccessibleName` / `setAccessibleDescription`. [SEVERITY: high]
  - LINE 29: `QLineEdit()` constructed with no parent argument. [SEVERITY: medium]
  - LINE 29: `self._input` missing `setAccessibleName` / `setAccessibleDescription`. [SEVERITY: high]
  - LINE 30: `QPushButton("Go")` constructed with no parent argument. [SEVERITY: medium]
  - LINE 30: `self._submit` missing `setAccessibleName` / `setAccessibleDescription`. [SEVERITY: high]
  - LINE 32: `setGeometry(10, 10, 200, 30)` — absolute positioning instead of a QLayout. [SEVERITY: high]
  - LINE 33: `setGeometry(220, 10, 60, 30)` — absolute positioning; not responsive/HiDPI-safe. [SEVERITY: high]
  - LINE 30: Button label "Go" is unlocalized and non-descriptive; would fail screen-reader clarity checks. [SEVERITY: low]
  - CLASS-LEVEL: No `QLayout` is ever installed on the widget, so children won't reflow on resize. [SEVERITY: high]
  - CLASS-LEVEL: No signal wiring (e.g., `clicked` / `returnPressed`) — the widget is functionally inert. [SEVERITY: low]

```json
{
  "known_good_widget.py": {"total_issues": 0, "issues": []},
  "known_bad_widget.py": {"total_issues": 13, "issues": [
    {"line": 20, "severity": "high", "description": "Hardcoded credential ADMIN_PASSWORD at module scope (Bandit B105)."},
    {"line": 23, "severity": "medium", "description": "LegacyForm class is missing a docstring."},
    {"line": 25, "severity": "low", "description": "__init__ lacks type hints on parent and return."},
    {"line": 26, "severity": "high", "description": "LegacyForm widget never calls setAccessibleName/setAccessibleDescription on self."},
    {"line": 29, "severity": "medium", "description": "QLineEdit() constructed without a parent argument."},
    {"line": 29, "severity": "high", "description": "self._input missing setAccessibleName/setAccessibleDescription."},
    {"line": 30, "severity": "medium", "description": "QPushButton('Go') constructed without a parent argument."},
    {"line": 30, "severity": "high", "description": "self._submit missing setAccessibleName/setAccessibleDescription."},
    {"line": 30, "severity": "low", "description": "Button label 'Go' is non-descriptive and unlocalized."},
    {"line": 32, "severity": "high", "description": "setGeometry used for absolute positioning instead of a QLayout."},
    {"line": 33, "severity": "high", "description": "setGeometry used for absolute positioning; not HiDPI/resize safe."},
    {"line": 0, "severity": "high", "description": "No QLayout installed on the widget; children will not reflow."},
    {"line": 0, "severity": "low", "description": "No signal wiring (clicked/returnPressed); widget is inert."}
  ]}
}
```

Usage: 38,188 subagent tokens; 2 tool uses; 21,233 ms.
