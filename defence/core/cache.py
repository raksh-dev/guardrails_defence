from collections import OrderedDict
from functools import wraps
from threading import Lock
from typing import Any, Callable


class LRUCache:
    """
    Thread-safe LRU cache backed by OrderedDict.
    Evicts the least-recently-used entry when maxsize is exceeded.
    """

    def __init__(self, maxsize: int = 500):
        self.maxsize = maxsize
        self._cache: OrderedDict[Any, Any] = OrderedDict()
        self._lock = Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def delete(self, key: Any) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# Singleton
book_cache = LRUCache(maxsize=500)


def cached(cache: LRUCache, key_arg: str):
    """
    Decorator that caches a method's return value in the given LRUCache.

    The cache key is taken from the argument named `key_arg`.
    The decorated method is only called on a cache miss.

    Usage:
        @cached(cache=book_cache, key_arg="book_id")
        def get_by_id_or_raise(self, book_id: int) -> BookResponse:
            ...

    To invalidate a cached entry, call cache.delete(key) directly
    in any method that mutates the underlying data.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            import inspect
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())

            if key_arg in kwargs:
                key = kwargs[key_arg]
            elif key_arg in params:
                idx = params.index(key_arg)
                key = args[idx]
            else:
                raise ValueError(
                    f"@cached: argument '{key_arg}' not found in "
                    f"function signature of '{fn.__name__}'"
                )

            # hit
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value

            # miss
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result

        return wrapper
    return decorator