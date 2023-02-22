from time import time
from unittest import mock

import pytest
import pytest_asyncio
from aioqzone.api.loginman import QrStrategy
from aioqzone.exception import LoginError, SkipLoginInterrupt
from qqqr.exception import TencentLoginError
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncEngineFactory
from sqlalchemy.ext.asyncio import AsyncEngine

from qzone3tg.app.base import BaseApp, TimeoutLoginman
from qzone3tg.settings import BotConf, QzoneConf, Settings

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module")
async def engine():
    async with AsyncEngineFactory.sqlite3(None) as engine:
        yield engine


mock_err = TencentLoginError(2333, "mock error")


async def test_suppress(client: ClientAdapter, engine: AsyncEngine):
    app = BaseApp(
        client,
        engine,
        Settings(
            qzone=QzoneConf(qq=1, qr_strategy=QrStrategy.forbid), bot=BotConf(admin=1)
        ).load_secrets(),
    )

    with mock.patch("qqqr.up.UpLogin.login", side_effect=mock_err):
        with pytest.raises(LoginError):
            await app.loginman._new_cookie()

    async def __coro():
        return None

    with mock.patch("telegram.Bot.send_message", return_value=__coro):
        await app.loginman.wait("hook")
    assert app.loginman.up_suppressed
    with pytest.raises(SkipLoginInterrupt):
        await app.loginman._new_cookie()


async def test_force(client: ClientAdapter, engine: AsyncEngine):
    lm = TimeoutLoginman(client, engine, 1, QrStrategy.allow, "pwd")
    lm.suppress_up_till = 3600 + time()
    with mock.patch("qqqr.up.UpLogin.login", side_effect=RuntimeError):
        with lm.disable_suppress():
            with pytest.raises(SystemExit):
                await lm.new_cookie()
