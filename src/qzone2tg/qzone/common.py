"""
Some constants.
"""

PROXY_DOMAIN = "https://user.qzone.qq.com/proxy/domain/"
COMPLETE_FEED_URL = PROXY_DOMAIN + "taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
DOLIKE_URL = PROXY_DOMAIN + "w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
UNLIKE_URL = PROXY_DOMAIN + "w.qzone.qq.com/cgi-bin/likes/internal_unlike_app"
GET_PAGE_URL = PROXY_DOMAIN + "ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
UPDATE_FEED_URL = PROXY_DOMAIN + "ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi"
PHOTO_LIST_URL = PROXY_DOMAIN + "plist.photo.qq.com/fcgi-bin/cgi_floatview_photo_list_v2"
MSG_DETAIL_URL = PROXY_DOMAIN + "taotao.qq.com/cgi-bin/emotion_cgi_msgdetail_v6"

BLOCK_LIST = [
    20050606,      # Qzone Official
]

Args4GettingFeeds = {
    'scope': 0,
    'view': 1,
    'daylist': '',
    'uinlist': '',
    'gid': '',
    'flag': 1,
    'filter': 'all',
    'applist': 'all',
    'refresh': 0,
    'aisortEndTime': 0,
    'aisortOffset': 0,
    'getAisort': 0,
    'aisortBeginTime': 0,
    'firstGetGroup': 0,
    'icServerTime': 0,
    'mixnocache': 0,
    'scene': 0,
    'dayspac': 'undefined',
    'sidomain': 'qzonestyle.gtimg.cn',
    'useutf8': 1,
    'outputhtmlfeed': 1,
}

Arg4CompleteFeed = {
    "pos": 0,
    "num": 1,
    "cmtnum": 1,
    "t1_source": 1,
    "who": 1,
    "inCharset": "utf-8",
    "outCharset": "utf-8",
    "plat": "qzone",
    "source": "ic",
    "paramstr": 1,
    "fullContent": 1,
}

Arg4ListPhoto = {
    'callback': 'viewer_Callback',
    'cmtOrder': 1,
    'fupdate': 1,
    'plat': 'qzone',
    'source': 'qzone',
    'cmtNum': 0,
    'likeNum': 0,
    'inCharset': 'utf-8',
    'outCharset': 'utf-8',
    'callbackFun': 'viewer',
    'offset': 0,
    'appid': 311,
    'isFirst': 1,
    'need_private_comment': 1,
}