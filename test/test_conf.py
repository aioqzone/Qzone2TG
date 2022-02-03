from os import environ as env
from pathlib import Path

import pytest

from qzone2tg.settings import Settings
from qzone2tg.settings import UserSecrets


@pytest.mark.skipif(not Path('config/test.yml').exists(), reason='test config not exist')
def test_load():
    import yaml
    with open('config/test.yml') as f:
        d = yaml.safe_load(f)
    assert Settings(**d).load_secrets(Path('./config/secrets'))


@pytest.mark.skipif('TEST_TOKEN' not in env, reason='test env not exist')
def test_secrets():
    sc = UserSecrets()    # type: ignore
