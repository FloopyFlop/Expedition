from __future__ import annotations

from collections import deque
from typing import Iterable

from .job.state import FrontierItem


class Frontier:
    def __init__(self, traversal: str, items: list[FrontierItem] | None = None) -> None:
        if traversal not in {"bfs", "dfs"}:
            raise ValueError(f"Unsupported traversal: {traversal}")
        self.traversal = traversal
        if traversal == "bfs":
            self._queue: deque[FrontierItem] = deque(items or [])
        else:
            self._stack: list[FrontierItem] = list(items or [])

    def __len__(self) -> int:
        if self.traversal == "bfs":
            return len(self._queue)
        return len(self._stack)

    def is_empty(self) -> bool:
        return len(self) == 0

    def push(self, item: FrontierItem) -> None:
        if self.traversal == "bfs":
            self._queue.append(item)
        else:
            self._stack.append(item)

    def push_many(self, items: Iterable[FrontierItem]) -> None:
        if self.traversal == "bfs":
            for item in items:
                self._queue.append(item)
        else:
            ordered = list(items)
            for item in reversed(ordered):
                self._stack.append(item)

    def pop(self) -> FrontierItem:
        if self.traversal == "bfs":
            return self._queue.popleft()
        return self._stack.pop()

    def to_list(self) -> list[FrontierItem]:
        if self.traversal == "bfs":
            return list(self._queue)
        return list(self._stack)
