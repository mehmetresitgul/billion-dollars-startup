class PaciforError(Exception):
    pass


class KillSwitchEngaged(PaciforError):
    def __init__(self, reason: str = "Kill switch is engaged"):
        self.reason = reason
        super().__init__(reason)


class HITLRejected(PaciforError):
    def __init__(self, review_id: str, node_name: str):
        self.review_id = review_id
        self.node_name = node_name
        super().__init__(f"HITL gate rejected at {node_name!r}, review_id={review_id}")


class RunNotFound(PaciforError):
    def __init__(self, run_id: str):
        super().__init__(f"Run {run_id!r} not found")
