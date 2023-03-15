from time import time
from unittest.mock import patch

import pytest
import pytest_asyncio
from aioqzone.event import LoginMethod
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
        Settings(qzone=QzoneConf(qq=1, qr_strategy="forbid"), bot=BotConf(admin=1)).load_secrets(),
    )

    from qqqr.up import UpWebLogin
    from telegram import Bot

    with patch.object(UpWebLogin, "login", side_effect=mock_err):
        with pytest.raises(LoginError):
            await app.loginman._new_cookie()

    with patch.object(Bot, "send_message"):
        await app.loginman.loginables[LoginMethod.up].wait("hook")  # type: ignore
    assert app.loginman.up_suppressed
    with pytest.raises(SkipLoginInterrupt):
        await app.loginman._new_cookie()


async def test_force(client: ClientAdapter, engine: AsyncEngine):
    from qqqr.up import UpWebLogin

    lm = TimeoutLoginman(client, engine, 1, [LoginMethod.up, LoginMethod.qr], "pwd")
    lm.suppress_up_till = 3600 + time()
    with patch.object(UpWebLogin, "login", side_effect=RuntimeError):
        with lm.disable_suppress(), pytest.raises(RuntimeError):
            await lm.new_cookie()
