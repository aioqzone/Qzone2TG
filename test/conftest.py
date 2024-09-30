import pytest_asyncio
from qqqr.utils.net import ClientAdapter


@pytest_asyncio.fixture(loop_scope="module")
async def client():
    async with ClientAdapter() as client:
        yield client
