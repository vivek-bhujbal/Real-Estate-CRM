"""Continuously expire due unit holds in small, lock-safe batches."""

import asyncio
import logging
import os
from pathlib import Path

from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.services.inventory import expire_due_holds

logger = logging.getLogger(__name__)
HEARTBEAT_PATH = Path(
    os.getenv("UNIT_HOLD_EXPIRY_HEARTBEAT_PATH", "/tmp/unit-hold-expiry.heartbeat")
)


def _write_heartbeat() -> None:
    """Record only successful cycles so Docker can detect a stalled/broken worker."""
    HEARTBEAT_PATH.touch()


async def run_once() -> int:
    total = 0
    while True:
        async with SessionFactory() as db:
            expired = await expire_due_holds(db, limit=200)
        total += expired
        if expired < 200:
            return total


async def main() -> None:
    configure_logging()
    interval = max(5, int(os.getenv("UNIT_HOLD_EXPIRY_INTERVAL_SECONDS", "30")))
    try:
        while True:
            try:
                expired = await run_once()
                _write_heartbeat()
                if expired:
                    logger.info("Expired %s unit holds", expired)
            except Exception:
                logger.exception("Unit-hold expiry cycle failed")
            await asyncio.sleep(interval)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
