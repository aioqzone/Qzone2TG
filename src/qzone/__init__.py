"""
qzone: 
    Fetch feeds from qzone, Along with qzone login and cookie management.
    
    credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py
"""

import json
import logging
import re
import time
from random import random
from typing import Any, Dict, List, Optional
from typing_extensions import ParamSpec
from urllib.parse import parse_qs, quote, unquote

from jssupport.jsjson import json_loads
from requests.exceptions import HTTPError

from qzone.cookie import QzLoginCookie

from .common import *
from .exceptions import QzoneError

logger = logging.getLogger(__name__)

PROXY_DOMAIN = "https://user.qzone.qq.com/proxy/domain/"
COMPLETE_FEED_URL = PROXY_DOMAIN + "taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
DOLIKE_URL = PROXY_DOMAIN + "w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
UNLIKE_URL = PROXY_DOMAIN + "w.qzone.qq.com/cgi-bin/likes/internal_unlike_app"
GET_PAGE_URL = PROXY_DOMAIN + "ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
UPDATE_FEED_URL = PROXY_DOMAIN + "ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi"
PHOTO_LIST_URL = PROXY_DOMAIN + "plist.photo.qq.com/fcgi-bin/cgi_floatview_photo_list_v2"

BLOCK_LIST = [
    20050606,      # Qzone Official
]

RE_CALLBACK = re.compile(r"callback\((\{.*\})", re.S | re.I)


def time_ms():
    return round(time.time() * 1000)


class QzoneScraper:
    lastHB: float = None

    def __init__(
        self,
        cookiestorage: QzLoginCookie,
    ):
        self.extern = {1: "undefined"}
        self.new_pred = None
        self.cookie = cookiestorage

        self.get = self.cookie.get
        self.post = self.cookie.post
        self.uin = self.cookie.uin

    def parseExternParam(self, page: int):
        unquoted = self.extern[page]
        if unquoted == "undefined": return {}
        return {k: v[-1] for k, v in parse_qs(unquoted, keep_blank_values=True).items()}

    def getCompleteFeed(self, feedData: dict) -> Optional[str]:
        if not feedData: return

        body = {
            "uin": feedData["uin"],
            "tid": feedData["tid"],
            "feedsType": feedData["feedstype"],
            "qzreferrer": f"https://user.qzone.qq.com/{self.uin}",
        }
        body.update(Arg4CompleteFeed)

        r = self.post(COMPLETE_FEED_URL, params={'g_tk': self.cookie.gtk}, data=body)
        if r is None: return

        r = RE_CALLBACK.search(r.text).group(1)
        r = json.loads(r)
        if r["err"] == 0: return r["newFeedXML"].strip()

    @QzLoginCookie.login_if_expire(False)
    def doLike(self, likedata: dict, like) -> bool:
        """like or unlike a post according to likedata

        - login_if_expire

        Args:
            likedata (dict): data contains essential args to like a post
            like (bool): True is like, False is unlike.

        Raises:
            QzoneError: Error from qzone interface

        Returns:
            bool: if success
        """
        body = {
            'qzreferrer': f'https://user.qzone.qq.com/{self.uin}',
            'opuin': self.uin,
            'from': 1,
            'active': 0,
            'fupdate': 1,
            'fid': likedata.get('key', None) or likedata.get('fid', None)
        }
        body.update(likedata)
        try:
            r = self.post(
                DOLIKE_URL if like else UNLIKE_URL,
                params={'g_tk': self.cookie.gtk},
                data=body
            )
        except HTTPError:
            return False
        if r is None: return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(RE_CALLBACK.search(r).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

    @QzLoginCookie.login_if_expire([])
    def fetchPage(
        self,
        pagenum: int,
        count: int = 10,
    ) -> List[Dict[str, Any]]:
        """fetch a page of feeds

        - login_if_expire
        
        Args:
            pagenum (int): page #, starts from 1.
            count (int, optional): Max feeds num. Defaults to 10.

        Raises:
            `UserBreak`: see `updateStatus`
            `LoginError`: see `updateStatus`
            `QzoneError`: exceptions that are raised by Qzone
            `TimeoutError`: if code -10001 is returned for 12 times.

        Returns:
            `list[Iterable[str, Any]]`, each dict reps a feed.
        """
        assert pagenum > 0

        query = {
            'rd': random(),
            'uin': self.uin,
            'pagenum': pagenum,
            'g_tk': self.cookie.gtk,
            'begintime': self.parseExternParam(pagenum).get("basetime", "undefined"),
            'count': count,
            'usertime': time_ms(),
            'externparam': quote(self.extern[pagenum])
        }
        query.update(Args4GettingFeeds)

        r = self.get(GET_PAGE_URL, params=query)
        if r is None: return []

        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)
        if r['code'] != 0:
            raise QzoneError(r['code'], r['message'])

        self.new_pred = 0
        data: dict = r['data']
        self.extern[pagenum + 1] = unquote(data['main']["externparam"])
        feeddict = filter(
            lambda i: not (
                not i or                                    # `undefined` in feed datas or empty feed dict
                i['key'].startswith('advertisement_app') or # ad feed
                int(i['appid']) >= 4096 or                  # not supported (cannot encode)
                int(i['uin']) in BLOCK_LIST or              # in blocklist
                int(i['uin']) == self.uin                   # is mine
            ),
            data['data']
        )
        return list(feeddict)

    @QzLoginCookie.login_if_expire(0)
    def checkUpdate(self) -> int:
        """return the predict of new feed amount.

        Raises:
            QzoneError: if unkown qzone code returned

        Returns:
            int: super of new feed amount
        """
        query = {'uin': self.uin, 'rd': random(), 'g_tk': self.cookie.gtk}
        r = self.get(UPDATE_FEED_URL, params=query)
        if r is None: return 0

        logger.debug('heartbeat OK')
        self.lastHB = time.time()

        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)
        if r["code"] != 0: raise QzoneError(r['code'], r['message'])

        r = r['data']
        cal_item = 'friendFeeds_new_cnt', 'friendFeeds_newblog_cnt', 'friendFeeds_newphoto_cnt', 'myFeeds_new_cnt'
        self.new_pred = sum(r[i] for i in cal_item)
        return self.new_pred

    def status(self):
        return {
            'last_heartbeat': self.lastHB,
            'last_login': self.cookie.lastLG,
        }

    def photoList(self, photo: Dict[str, Any], num: int):
        query = {
            'g_tk': self.cookie.gtk,
            'topicId': photo['topicid'],
            'picKey': photo['pickey'],
            'hostUin': photo['hostuin'],
            'number': num,
            'uin': self.uin,
            '_': time_ms(),
        }
        query.update(Arg4ListPhoto)
        r = self.get(PHOTO_LIST_URL, params=query)
        r = RE_CALLBACK.search(r.text)
        r = json_loads(r)

        if r['code'] != 0: raise QzoneError(r['code'], r['message'])
        r = r['data']['photos']

        rd = lambda d: {k: d[k] for k in ['pre', 'picId', 'url']}
        return [rd(i) for i in r]
