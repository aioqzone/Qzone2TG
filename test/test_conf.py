from os import environ as env
from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from qzone3tg.settings import Settings, UserSecrets, WebhookConf


@pytest.mark.skipif(not Path("config/test.yml").exists(), reason="test config not exist")
def test_load():
    with open("config/test.yml") as f:
        mind, maxd = yaml.safe_load_all(f)
    minc = Settings(**mind)
    maxc = Settings(**maxd)


@pytest.mark.skipif("TEST_TOKEN" not in env, reason="test env not exist")
def test_secrets():
    sc = UserSecrets()  # type: ignore


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
