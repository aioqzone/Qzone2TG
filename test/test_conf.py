from http import client
from os import environ as env
from pathlib import Path

import pytest
import qzemoji as qe
import yaml
from httpx import AsyncClient
from pydantic import SecretStr
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncEngineFactory

from qzone3tg.settings import Settings, UserSecrets, WebhookConf

if_conf_exist = pytest.mark.skipif(
    not Path("config/test.yml").exists(), reason="test config not exist"
)


@if_conf_exist
def test_load():
    with open("config/test.yml") as f:
        mind, maxd = yaml.safe_load_all(f)
    minc = Settings(**mind)
    maxc = Settings(**maxd)
    assert minc
    assert maxc


@pytest.mark.skipif("TEST_TOKEN" not in env, reason="test env not exist")
def test_secrets():
    sc = UserSecrets()  # type: ignore
    assert sc


def test_webhook_url():
    wh = WebhookConf.parse_obj(dict(destination="https://example.xyz/prefix/"))
    url = wh.webhook_url(SecretStr("hello")).get_secret_value()
    assert url == "https://example.xyz/prefix/hello"
    wh = WebhookConf.parse_obj(dict(destination="https://example.xyz/prefix"))
    url = wh.webhook_url(SecretStr("hello")).get_secret_value()
    assert url == "https://example.xyz/prefix/hello"
    wh = WebhookConf.parse_obj(dict(destination="https://example.xyz"))
    url = wh.webhook_url(SecretStr("hello")).get_secret_value()
    assert url == "https://example.xyz/hello"


@if_conf_exist
@pytest.mark.asyncio
async def test_init():
    from qzone3tg.app.interact import InteractApp

    with open("config/test.yml") as f:
        mind, maxd = yaml.safe_load_all(f)

    minc = Settings(**mind).load_secrets()
    maxc = Settings(**maxd).load_secrets()
    async with AsyncClient() as sess, AsyncEngineFactory.sqlite3(None) as engine:
        client = ClientAdapter(sess)
        InteractApp(client, engine, conf=minc)
        InteractApp(client, engine, conf=maxc)
        assert qe.proxy == "socks5://localhost:443"


@if_conf_exist
@pytest.mark.asyncio
async def test_hook_class():
    from qzone3tg.app.base import (
        BaseApp,
        DefaultFeedHook,
        DefaultQrHook,
        DefaultStorageHook,
        DefaultUpHook,
        TaskerEvent,
    )
    from qzone3tg.app.interact import InteractApp

    with open("config/test.yml") as f:
        mind, _ = yaml.safe_load_all(f)

    minc = Settings(**mind).load_secrets()
    async with AsyncClient() as sess, AsyncEngineFactory.sqlite3(None) as engine:
        client = ClientAdapter(sess)
        bapp = BaseApp(client, engine, conf=minc)
        assert bapp.sub_of(DefaultFeedHook).__qualname__.startswith(BaseApp.__qualname__)
        assert bapp.sub_of(DefaultQrHook).__qualname__.startswith(BaseApp.__qualname__)

        iapp = InteractApp(client, engine, conf=minc)
        assert iapp.sub_of(DefaultFeedHook).__qualname__.startswith(InteractApp.__qualname__)
        assert iapp.sub_of(DefaultQrHook).__qualname__.startswith(InteractApp.__qualname__)
        assert iapp.hook_qr.qr_markup.__qualname__.startswith(InteractApp.__qualname__)
