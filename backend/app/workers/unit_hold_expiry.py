"""Continuously expire due unit holds in small, lock-safe batches."""

import asyncio
import logging
import os

from app.db.session import SessionFactory, engine
from app.services.inventory import expire_due_holds

logger = logging.getLogger(__name__)


async def run_once() -> int:
    total = 0
    while True:
        async with SessionFactory() as db:
            expired = await expire_due_holds(db, limit=200)
        total += expired
        if expired < 200:
            return total


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    interval = max(5, int(os.getenv("UNIT_HOLD_EXPIRY_INTERVAL_SECONDS", "30")))
    try:
        while True:
            try:
                expired = await run_once()
                if expired:
                    logger.info("Expired %s unit holds", expired)
            except Exception:
                logger.exception("Unit-hold expiry cycle failed")
            await asyncio.sleep(interval)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
