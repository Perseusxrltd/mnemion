"""Fair, sequential indexing across configured models with bounded backfill."""

from .model_registry import ModelRegistry
from .reindex import ReindexBackfill
from .worker import Worker


class ModelWorker:
    def __init__(self, database, registry: ModelRegistry, *, telemetry=None):
        self.backfill = ReindexBackfill(database, registry)
        self.workers = [
            Worker(
                database,
                registry.get(generation),
                telemetry=telemetry,
                default_generation=registry.default.generation.id,
            )
            for generation in registry.generation_ids
        ]
        self.next_worker = 0

    def run_once(self) -> bool:
        backfilled = self.backfill.run_once()
        for _ in self.workers:
            worker = self.workers[self.next_worker]
            self.next_worker = (self.next_worker + 1) % len(self.workers)
            if worker.run_once():
                return True
        return backfilled
