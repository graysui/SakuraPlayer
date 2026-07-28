from __future__ import annotations

from typing import Protocol


class CachePipeline(Protocol):
    def run_once(self, *, worker_id: str) -> str: ...


class CacheStartupRecovery:
    def __init__(self, pipeline: CachePipeline, *, max_operations: int = 100) -> None:
        if not 1 <= max_operations <= 100:
            raise ValueError("max_operations must be 1..100")
        self._pipeline = pipeline
        self._max_operations = max_operations

    def run(self, *, worker_id: str) -> int:
        recovered = 0
        for _ in range(self._max_operations):
            outcome = self._pipeline.run_once(worker_id=worker_id)
            if outcome == "idle":
                break
            if outcome != "worked":
                raise ValueError("invalid cache pipeline outcome")
            recovered += 1
        return recovered


__all__ = ["CacheStartupRecovery"]
