import copy
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import pydantic


class ManualClock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


@dataclass
class _CacheEntry:
    value: object
    expires_at: float


class ExpiringCache:
    def __init__(self, clock: ManualClock | None = None) -> None:
        self.clock = clock or ManualClock()
        self.entries: dict[str, _CacheEntry] = {}
        self.available = True

    async def get(self, key: str) -> object | None:
        if not self.available:
            raise ConnectionError("cache boundary unavailable")
        entry = self.entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self.clock.seconds:
            del self.entries[key]
            return None
        return copy.deepcopy(entry.value)

    async def set(self, key: str, value: object, *, ttl: int) -> bool:
        if not self.available:
            raise ConnectionError("cache boundary unavailable")
        self.entries[key] = _CacheEntry(
            value=copy.deepcopy(value),
            expires_at=self.clock.seconds + ttl,
        )
        return True

    def corrupt_values(
        self,
        predicate: Callable[[object], bool],
        replacement: object,
    ) -> None:
        for entry in self.entries.values():
            if predicate(entry.value):
                entry.value = replacement

    def corrupt_cached_model(
        self,
        model_type: type[pydantic.BaseModel],
        replacement: object,
    ) -> None:
        matching_entries: list[_CacheEntry] = []
        for entry in self.entries.values():
            try:
                model_type.model_validate(entry.value)
            except TypeError, pydantic.ValidationError:
                continue
            matching_entries.append(entry)

        if len(matching_entries) != 1:
            raise AssertionError(f"expected exactly one cached {model_type.__name__}, found {len(matching_entries)}")
        matching_entries[0].value = copy.deepcopy(replacement)


class InvalidCache:
    def __init__(self, value: object) -> None:
        self.value = value

    async def get(self, _key: str) -> object:
        return self.value

    async def set(self, _key: str, _value: object, *, ttl: int) -> bool:
        return True


class OpaqueAIQueue:
    def __init__(
        self,
        responses: Iterable[object] = (),
        *,
        empty_exception: BaseException | None = None,
    ) -> None:
        self.responses = deque(responses)
        self.empty_exception = empty_exception or OSError("AI boundary unavailable")

    async def __call__(self, *_args, **_kwargs):
        if not self.responses:
            raise self.empty_exception
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return copy.deepcopy(response)
