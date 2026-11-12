def normalize_status(status):
    if status == "new":
        return "queued"
    if status == "queued":
        return "running"
    if status == "running":
        return "done"
    if status == "failed":
        return "retry"
    if status == "cancelled":
        return "closed"
    return "unknown"
