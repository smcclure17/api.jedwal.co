import dataclasses
from typing import TypeVar

T = TypeVar("T")


@dataclasses.dataclass
class LRUCache:
    """Simple LRU cache implementation.

    Args:
        capacity: Maximum number of items to store.
    """

    capacity: int
    cache: dict = dataclasses.field(default_factory=dict)
    order: list = dataclasses.field(default_factory=list)

    def get(self, key: str) -> T:
        """Get item from cache.

        Args:
            key: Key to get.

        Returns: Value if exists, None if missing.
        """
        if key in self.cache:
            self.order.remove(key)
            self.order.append(key)
            return self.cache[key]
        return None

    def put(self, key: str, value: T) -> None:
        """Add item to cache.

        Args:
            key: Key to add.
            value: Value to add.
        """
        if key in self.cache:
            self.order.remove(key)
        elif len(self.cache) >= self.capacity:
            del self.cache[self.order.pop(0)]
        self.cache[key] = value
        self.order.append(key)
