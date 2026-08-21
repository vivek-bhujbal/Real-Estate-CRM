import os
import tempfile
from collections.abc import AsyncIterator
from itertools import count

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-with-at-least-thirty-two-characters"
os.environ["STORAGE_LOCAL_PATH"] = tempfile.mkdtemp(prefix="realestate-crm-test-files-")

from app.db import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

client_number = count(1)


@pytest_asyncio.fixture(autouse=True)
async def database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, client=(f"test-client-{next(client_number)}", 123))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
