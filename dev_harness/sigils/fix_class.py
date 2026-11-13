"""`FOLLOW_ON` names the rule that follows a ruff finding of each fix class."""

FOLLOW_ON = {
    "always": "apply ruff's fix for that rule and read the file again",
    "sometimes": "the same, where ruff offers it for that line",
    "none": "a unit of work",
}
BY_FIX_CLASS = "; by fix class: " + "; ".join(
    f"{fix} -> {rule}" for fix, rule in FOLLOW_ON.items()
)
