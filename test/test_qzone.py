import os
import sqlite3
from pathlib import Path

import pytest
from middleware.storage import TokenTable
from omegaconf import OmegaConf
from qzone.exceptions import LoginError
from qzone.parser import QZFeedParser
from qzone.scraper import QzoneScraper

db = spider = FEEDS = None


def load_conf():
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


def setup_module():
    global db, spider
    Path('data').mkdir(exist_ok=True)
    db = sqlite3.connect('data/test.db', check_same_thread=False)
    spider = QzoneScraper(TokenTable(db), **load_conf().qzone)


def test_UpdateStatus():
    global login
    try:
        spider.updateStatus(force_login=True)
        login = True
    except LoginError:
        login = False
        pytest.skip('Account banned.', allow_module_level=True)


def test_checkUpdate():
    if login is None: test_checkUpdate()
    if login == False: pytest.skip('not login', allow_module_level=True)
    spider.checkUpdate()


def test_FetchPage():
    if login is None: test_checkUpdate()
    if login == False: pytest.skip('not login', allow_module_level=True)
    global FEEDS
    feeds = spider.fetchPage(1, 1)
    assert feeds is not None
    assert 0 < len(feeds) <= 10
    feeds.extend(spider.fetchPage(2))
    FEEDS = [QZFeedParser(i) for i in feeds]


def test_GetFullContent():
    if FEEDS is None: pytest.skip('pred test failed.')
    hit = False
    for i in FEEDS:
        if not i.isCut(): continue
        spider.getCompleteFeed(i.feedData)
        hit = True
    if not hit: pytest.skip('no sample crawled')


def test_doLike():
    if FEEDS is None: pytest.skip('pred test failed.')
    if not FEEDS: pytest.skip('pred test failed')
    for i in FEEDS:
        d = i.getLikeId()
        if i.isLike:
            assert spider.doLike(d, False)
            assert spider.doLike(d, True)
        else:
            assert spider.doLike(d, True)
            assert spider.doLike(d, False)
        return
    else:
        pytest.skip('no sample crawled')


def teardown_module() -> None:
    global db
    return db.close()
