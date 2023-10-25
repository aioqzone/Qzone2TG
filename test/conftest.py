import asyncio

import pytest
import pytest_asyncio
from qqqr.utils.net import ClientAdapter


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def client():
    async with ClientAdapter() as client:
        yield client
