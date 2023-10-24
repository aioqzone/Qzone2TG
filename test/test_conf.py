from os import environ as env
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from pydantic import SecretStr
from qzemoji.base import AsyncEngineFactory

from qzone3tg.app.base import BaseApp
from qzone3tg.app.interact import InteractApp
from qzone3tg.settings import Settings, UserSecrets, WebhookConf

if_conf_exist = pytest.mark.skipif(
    not Path("config/test.yml").exists(), reason="test config not exist"
)


@pytest.fixture(scope="module")
def minc():
    with open("config/test.yml") as f:
        mind, _ = yaml.safe_load_all(f)
    return Settings(**mind).load_secrets()


@pytest_asyncio.fixture(scope="module")
async def engine():
    async with AsyncEngineFactory.sqlite3(None) as engine:
        yield engine


@if_conf_exist
def test_load(minc: Settings):
    assert minc

    with open("config/test.yml") as f:
        _, maxd = yaml.safe_load_all(f)
    maxc = Settings(**maxd)
    assert maxc


@pytest.mark.skip
def test_env():
    from os import environ as env

    env["qzone.qq"] = "123"
    env["bot.admin"] = "456"
    env["bot.init_args.port"] = "8443"
    env["bot.init_args.destination"] = "https://example.xyz/prefix"

    conf = Settings(**{}).load_secrets()

    assert conf.qzone.uin == 123
    assert conf.bot.admin == 456
    assert isinstance(conf.bot.init_args, WebhookConf)


@pytest.mark.skipif("TEST_TOKEN" not in env, reason="test env not exist")
def test_secrets():
    sc = UserSecrets()  # type: ignore
    assert sc.token
    assert sc.password


def test_webhook_url():
    wh = WebhookConf.model_validate(dict(destination="https://example.xyz/prefix/"))
    url = wh.webhook_url(SecretStr("hello")).get_secret_value()
    assert url == "https://example.xyz/prefix/hello"
    wh = WebhookConf.model_validate(dict(destination="https://example.xyz/prefix"))
    url = wh.webhook_url(SecretStr("hello")).get_secret_value()
    assert url == "https://example.xyz/prefix/hello"
    wh = WebhookConf.model_validate(dict(destination="https://example.xyz"))
    url = wh.webhook_url(SecretStr("hello")).get_secret_value()
    assert url == "https://example.xyz/hello"


@if_conf_exist
@pytest.mark.asyncio
async def test_init(minc: Settings):
    from qzone3tg.app.interact import InteractApp

    with open("config/test.yml") as f:
        _, maxd = yaml.safe_load_all(f)

    maxc = Settings(**maxd).load_secrets()
    async with InteractApp(conf=minc):
        pass
    async with InteractApp(conf=maxc):
        pass
    # assert qe.proxy == "socks5://localhost:443"


@pytest.mark.asyncio
async def test_base_hook(minc: Settings):
    async with BaseApp(minc) as app:
        assert app._uplogin.login_failed.has_impl
        assert app._uplogin.login_success.has_impl
        assert app.qzone.feed_processed.has_impl
        assert app.qzone.feed_dropped.has_impl
        assert "local" in app.qzone.stop_fetch.__qualname__
        assert app.qzone.hb_failed.has_impl
        assert app.qzone.hb_refresh.has_impl


@pytest.mark.asyncio
async def test_interact_hook(minc: Settings):
    async with InteractApp(minc) as app:
        assert app._qrlogin.login_failed.has_impl
        assert app._qrlogin.login_success.has_impl
        assert app._qrlogin.qr_fetched.has_impl
        assert app._uplogin.sms_code_input.has_impl
