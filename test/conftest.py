import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient
from qqqr.utils.net import ClientAdapter


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def client():
    async with AsyncClient() as client:
        yield ClientAdapter(client)
