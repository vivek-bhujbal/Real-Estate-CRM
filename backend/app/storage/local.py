import asyncio
import shutil
from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _safe_path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Invalid storage key")
        return target

    async def save(self, *, key: str, source: Path) -> str:
        target = self._safe_path(key)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, target)
        return key

    async def delete(self, *, key: str) -> None:
        target = self._safe_path(key)
        if target.exists():
            await asyncio.to_thread(target.unlink)
