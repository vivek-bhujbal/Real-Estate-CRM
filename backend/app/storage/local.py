import asyncio
import os
import shutil
import uuid
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
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(shutil.copyfile, source, temporary)
            await asyncio.to_thread(os.replace, temporary, target)
            await asyncio.to_thread(os.chmod, target, 0o600)
        finally:
            if temporary.exists():
                await asyncio.to_thread(temporary.unlink)
        return key

    async def save_bytes(self, *, key: str, content: bytes) -> str:
        target = self._safe_path(key)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(temporary.write_bytes, content)
            await asyncio.to_thread(os.replace, temporary, target)
            await asyncio.to_thread(os.chmod, target, 0o600)
        finally:
            if temporary.exists():
                await asyncio.to_thread(temporary.unlink)
        return key

    async def delete(self, *, key: str) -> None:
        target = self._safe_path(key)
        if target.exists():
            await asyncio.to_thread(target.unlink)

    async def path_for_read(self, *, key: str) -> Path:
        target = self._safe_path(key)
        exists = await asyncio.to_thread(target.is_file)
        if not exists:
            raise FileNotFoundError(key)
        return target
