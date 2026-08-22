"""Release smoke checks intended for an isolated, newly migrated database."""

import asyncio
import sys

from sqlalchemy import func, select

from app.db.session import SessionFactory, engine
from app.models.entities import (
    Booking,
    ChannelPartner,
    Customer,
    Lead,
    Lease,
    Organization,
    Payment,
    Project,
    Quotation,
    RentalProperty,
    ServiceRequest,
    SiteVisit,
    Unit,
    UnitHold,
    User,
)

BUSINESS_MODELS = (
    Organization,
    User,
    Lead,
    Customer,
    Project,
    Unit,
    SiteVisit,
    Quotation,
    UnitHold,
    Booking,
    Payment,
    ChannelPartner,
    RentalProperty,
    Lease,
    ServiceRequest,
)


async def assert_empty_database() -> None:
    populated: dict[str, int] = {}
    async with SessionFactory() as db:
        for model in BUSINESS_MODELS:
            count = int(await db.scalar(select(func.count()).select_from(model)) or 0)
            if count:
                populated[model.__tablename__] = count
    await engine.dispose()
    if populated:
        details = ", ".join(f"{table}={count}" for table, count in populated.items())
        raise RuntimeError(f"Expected an empty release database; found business rows: {details}")


def main() -> int:
    if sys.argv[1:] != ["assert-empty"]:
        print("Usage: python -m app.deployment_checks assert-empty", file=sys.stderr)
        return 2
    asyncio.run(assert_empty_database())
    print("Empty-database assertion passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
