from pathlib import Path

import pytest

from qzone2tg.conf import Settings

pytestmark = pytest.mark.skipif(
    not Path('config/test.yml').exists(), reason='test config not exist'
)


def test_load():
    import yaml
    with open('config/test.yml') as f:
        d = yaml.safe_load(f)
    assert Settings(**d).load_secrets(Path('./config/secrets'))
