from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    async def save(self, *, key: str, source: Path) -> str: ...

    async def delete(self, *, key: str) -> None: ...
