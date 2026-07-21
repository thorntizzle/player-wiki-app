from __future__ import annotations

import os
from threading import BoundedSemaphore


DEFAULT_CHARACTER_READ_CAPACITY = 2
MAX_CHARACTER_READ_CAPACITY = 2
CHARACTER_READ_CAPACITY_ENV = "PLAYER_WIKI_CHARACTER_READ_MAX_CONCURRENT"


def resolve_character_read_capacity(value: object | None = None) -> int:
    raw_value = os.getenv(CHARACTER_READ_CAPACITY_ENV) if value is None else value
    try:
        capacity = int(raw_value) if raw_value is not None else DEFAULT_CHARACTER_READ_CAPACITY
    except (TypeError, ValueError):
        capacity = DEFAULT_CHARACTER_READ_CAPACITY
    return min(MAX_CHARACTER_READ_CAPACITY, max(1, capacity))


class CharacterReadAdmission:
    def __init__(self, capacity: int = DEFAULT_CHARACTER_READ_CAPACITY) -> None:
        self.capacity = resolve_character_read_capacity(capacity)
        self._semaphore = BoundedSemaphore(self.capacity)

    def try_acquire(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        self._semaphore.release()
