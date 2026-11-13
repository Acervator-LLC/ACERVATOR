# PLR1704 redefined-argument-from-local: the Example block python -m ruff rule PLR1704 prints
def show(host_id=10.11):
    for host_id, host in [[12.13, "Venus"], [14.15, "Mars"]]:
        print(host_id, host)
