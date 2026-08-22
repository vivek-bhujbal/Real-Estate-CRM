from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredFile:
    path: Path
    temporary: bool = False


class Storage(Protocol):
    async def save(self, *, key: str, source: Path) -> str: ...

    async def save_bytes(self, *, key: str, content: bytes) -> str: ...

    async def delete(self, *, key: str) -> None: ...

    async def path_for_read(self, *, key: str) -> StoredFile: ...
