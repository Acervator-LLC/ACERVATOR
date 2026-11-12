STATUS_TRANSITIONS = {
    "new": "queued",
    "queued": "running",
    "running": "done",
    "failed": "retry",
    "cancelled": "closed",
}


def normalize_status(status):
    return STATUS_TRANSITIONS.get(status, "unknown")
