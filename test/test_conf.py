from os import environ as env
from pathlib import Path

import pytest
import qzemoji
import yaml
from aiohttp import ClientSession
from pydantic import SecretStr

from qzone3tg.settings import Settings, UserSecrets, WebhookConf

testfile = pytest.mark.skipif(not Path("config/test.yml").exists(), reason="test config not exist")


@testfile
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


@testfile
@pytest.mark.asyncio
async def test_init():
    from qzone3tg.app.interact import InteractApp
    from qzone3tg.app.storage import AsyncEnginew

    with open("config/test.yml") as f:
        mind, maxd = yaml.safe_load_all(f)

    minc = Settings(**mind).load_secrets()
    maxc = Settings(**maxd).load_secrets()
    async with ClientSession() as sess, AsyncEnginew.sqlite3(None) as engine:
        InteractApp(sess, engine, conf=minc)
        InteractApp(sess, engine, conf=maxc)
