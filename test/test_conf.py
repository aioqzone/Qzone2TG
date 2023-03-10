from os import environ as env
from pathlib import Path

import pytest
import pytest_asyncio
import qzemoji as qe
import yaml
from aioqzone.event import QREvent, UPEvent
from aioqzone_feed.event import FeedEvent, HeartbeatEvent
from httpx import AsyncClient
from pydantic import SecretStr
from qqqr.event import Event
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncEngineFactory
from sqlalchemy.ext.asyncio import AsyncEngine

from qzone3tg.app.base import BaseApp, QueueEvent, StorageEvent
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


@pytest.mark.skipif("TEST_TOKEN" not in env, reason="test env not exist")
def test_secrets():
    sc = UserSecrets()  # type: ignore
    assert sc.token
    assert sc.password


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
async def test_init(minc: Settings):
    from qzone3tg.app.interact import InteractApp

    with open("config/test.yml") as f:
        _, maxd = yaml.safe_load_all(f)

    maxc = Settings(**maxd).load_secrets()
    async with AsyncClient() as sess, AsyncEngineFactory.sqlite3(None) as engine:
        client = ClientAdapter(sess)
        InteractApp(client, engine, conf=minc)._tasks
        InteractApp(client, engine, conf=maxc)._tasks
        assert qe.proxy == "socks5://localhost:443"


@if_conf_exist
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ["app_cls", "evt_cls"],
    [
        (BaseApp, FeedEvent),
        (BaseApp, HeartbeatEvent),
        (BaseApp, QREvent),
        (BaseApp, UPEvent),
        (BaseApp, QueueEvent),
        (BaseApp, StorageEvent),
        (InteractApp, HeartbeatEvent),
        (InteractApp, QREvent),
        (InteractApp, UPEvent),
        (InteractApp, QueueEvent),
    ],
)
async def test_hook_class(
    minc: Settings,
    client: ClientAdapter,
    engine: AsyncEngine,
    app_cls: type[BaseApp],
    evt_cls: type[Event],
):
    app = app_cls(client, engine, conf=minc)
    assert app[evt_cls].__class__.__name__ == (app_cls.__name__ + "_" + evt_cls.__name__).lower()
