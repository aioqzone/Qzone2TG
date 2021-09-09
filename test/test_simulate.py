import os
import pytest

from frontend.tg.ui import TgExtracter
from middleware.storage import FeedBase, TokenTable
from omegaconf import OmegaConf
from qzone import QzoneScraper
from qzone.exceptions import LoginError
from qzone.feed import QZCachedScraper

login = FEEDS = None


def load_conf():
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


def setup_module() -> None:
    global db, spider
    db = FeedBase('data/test.db', plugins={'tg': {'is_sent': 'BOOLEAN default 0'}})
    spider = QzoneScraper(token_tbl=TokenTable(db.cursor), **load_conf().qzone)
    spider = QZCachedScraper(spider, db)


def test_Fetch():
    global login
    try:
        spider.qzone.updateStatus()
        login = True
    except LoginError:
        login = False
        pytest.skip('Account banned.', allow_module_level=True)
    assert spider.getFeedsInPage(1, True)
    assert spider.getFeedsInPage(2, True)


def test_New():
    if not login: pytest.skip('not login', allow_module_level=True)
    global FEEDS
    FEEDS = None
    FEEDS = db.getFeed(
        cond_sql='is_sent IS NULL OR is_sent=0',
        plugin_name='tg',
        order=True,
    )
    assert isinstance(FEEDS, list)


def test_Extract():
    if not FEEDS: pytest.skip('pred test failed.')
    for i in FEEDS:
        i = TgExtracter(i, spider.qzone.uin)
        msg, img = i.content()
        assert msg
        assert isinstance(img, list)


def teardown_module():
    db.close()
