from collections import defaultdict
from datetime import datetime, timezone


class InMemoryRepository:
    def __init__(self) -> None:
        self.organizations: dict[str, dict] = {}
        self.services: dict[str, dict] = {}
        self.idempotency: dict[str, dict] = {}
        self.product_instances: dict[str, dict] = {}
        self.groups = defaultdict(set)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


repo = InMemoryRepository()
