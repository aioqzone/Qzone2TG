from unittest import mock

import pytest
from aioqzone.api.loginman import QrStrategy
from aioqzone.exception import SkipLoginInterrupt
from qqqr.utils.net import ClientAdapter
from sqlalchemy.ext.asyncio import AsyncEngine

from qzone3tg.app.base import TimeoutLoginman

pytestmark = pytest.mark.asyncio


@pytest.fixture
def engine() -> AsyncEngine:
    return  # type: ignore


class mock_trigger(RuntimeError):
    pass


async def test_suppress(client: ClientAdapter, engine: AsyncEngine):
    lm = TimeoutLoginman(client, engine, 1, QrStrategy.allow, "pwd")

    with mock.patch("aioqzone.api.loginman.UPLoginMan._new_cookie", side_effect=mock_trigger()):
        with pytest.raises(mock_trigger):
            await lm.new_cookie()
        with pytest.raises(SkipLoginInterrupt):
            await lm.new_cookie()


async def test_force(client: ClientAdapter, engine: AsyncEngine):
    lm = TimeoutLoginman(client, engine, 1, QrStrategy.allow, "pwd")

    with mock.patch("aioqzone.api.loginman.UPLoginMan._new_cookie", side_effect=mock_trigger()):
        with pytest.raises(mock_trigger):
            await lm.new_cookie()
        with lm.disable_suppress():
            with pytest.raises(mock_trigger):
                await lm.new_cookie()
