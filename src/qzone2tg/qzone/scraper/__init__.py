"""
qzone: 
    Fetch feeds from qzone, Along with qzone login and cookie management.
    
    credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py
"""

import json
import logging
import re
import time
from random import randint, random
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote

from jssupport.jsjson import json_loads
from requests.exceptions import HTTPError

from ...qzone.heartbeat import HBMgr
from ...utils.decorator import Retry
from ..common import *
from ..exceptions import QzoneError
from .album import AlbumQue

logger = logging.getLogger(__name__)

RE_CALLBACK = re.compile(r"callback\((\{.*\})", re.S | re.I)


def time_ms():
    return round(time.time() * 1000)


class QzoneScraper(HBMgr):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extern = {1: "undefined"}
        self.new_pred = None
        self.photoList = AlbumQue(self._photoList)

    def stop(self):
        self.photoList.stop()

    def _register_error_handler(self):
        super()._register_error_handler()
        excc = {QzoneError: self._login_if_expire, HTTPError: self._login_if_expire}
        for f, er in {self.fetchPage: [], self.doLike: False,
                      self._photoList: []}.items():
            setattr(self, f.__name__, Retry(excc.copy(), excr=er)(f))

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

        r = self.post(COMPLETE_FEED_URL, params={'g_tk': self.gtk}, data=body)
        if r is None: return

        r = RE_CALLBACK.search(r.text).group(1)
        r = json.loads(r)
        if r["err"] == 0: return r["newFeedXML"].strip()

    def doLike(self, likedata: dict, like) -> bool:
        """like or unlike a post according to likedata

        - login_if_expire

        Args:
            likedata (dict): data contains essential args to like a post
            like (bool): True is like, False is unlike.

        Raises:
            HTTPError: as it is
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
                params={'g_tk': self.gtk},
                data=body
            )
        except HTTPError:
            return False
        if r is None: return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(RE_CALLBACK.search(r).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

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
            `HTTPError`: as it is
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
            'g_tk': self.gtk,
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

    def checkUpdate(self) -> int:
        """return the predict of new feed amount.

        Raises:
            `HTTPError`: as it is
            `QzoneError`: if unknown qzone code returned

        Returns:
            `int`: super of new feed amount
        """
        SUM_ITEM = 'friendFeeds_new_cnt', 'friendFeeds_newblog_cnt'

        def predNewAmount(r: str):
            r = RE_CALLBACK.search(r).group(1)
            r = json_loads(r)
            if r["code"] != 0: raise QzoneError(r['code'], r['message'])

            r: dict[str, int] = r['data']
            self.new_pred = sum(r[i] for i in SUM_ITEM)
            return self.new_pred

        return super().checkUpdate(predNewAmount)

    def _photoList(self, album: Dict[str, Any], hostuin: int, num: int):
        """get photolist of an album

        - login_if_expire

        Args:
            album (Dict[str, Any]): album attrib. needs `topicid` & `pickey`
            hostuin (int): album owner uin
            num (int): num limit

        Raises:
            HTTPError: as it is
            QzoneError: if qzone returns an error code
            RuntimeError: if the request or response is modified(hooked) in transport

        Returns:
            list[dict[str, str]]: photolist, each `photo` is a dict[str, str]: key->url
        """
        query = {
            'g_tk': self.gtk,
            'topicId': album['topicid'],
            'picKey': album['pickey'],
            'hostUin': hostuin,
            'number': num,
            'uin': self.uin,
            '_': time_ms(),
            't': randint(1e8, 1e9 - 1)         # The distribution is not consistent
                                               # with photo.js; but the format is.
        }
        query.update(Arg4ListPhoto)
        r = self.get(PHOTO_LIST_URL, params=query)
        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)

        if r['code'] != 0: raise QzoneError(r['code'], r['message'])
        r = r['data']
        if query['t'] != int(r['t']):
            raise RuntimeError('Something unexpected occured in transport.')
        r = r['photos']

        def rd(d: dict):
            if d.get('is_video', 0) and 'video_info' in d:
                return {
                    'pre': d['url'],
                    'picId': d['picId'],
                    'url': d['video_info']['video_url']
                }
            else:
                return {k: d[k] for k in ['pre', 'picId', 'url']}

        return [rd(i) for i in r]

    def getFeedDetail(self, uin: int, fid: str) -> dict[str, Any]:
        """get feed detail

        Args:
            uin (int): owner uin
            fid (str): feed id. only feeds, not share.

        Returns:
            dict[str, Any]: [description]
        """
        data = {
            'uin': uin,
            'tid': fid,
            't1_source': 1,
            'ftype': 0,
            'sort': 0,
            'pos': 0,
            'num': 20,
            'g_tk': self.gtk,
            'callback': 'callback',
            'code_version': 1,
            'format': 'jsonp',
            'need_private_comment': 1,
        }
        r = self.get(MSG_DETAIL_URL, params=data)
        r = RE_CALLBACK.search(r.text).group(1)
        return json_loads(r)