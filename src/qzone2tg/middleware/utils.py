import time
from datetime import datetime

from pytz import timezone

TIME_ZONE = timezone('Asia/Shanghai')


def sementicTime(timestamp: int):
    feedtime = datetime.fromtimestamp(timestamp, TIME_ZONE)
    d = datetime.now(TIME_ZONE) - feedtime
    ch = ['', '昨天 ', '前天 ']
    s = ''
    if d.days <= 2: s += ch[d.days]
    else: s += feedtime.strftime('%m月%d日 ')
    s += feedtime.strftime('%H:%M')
    return s

def day_stamp(timestamp: float = None) -> int:
    if timestamp is None: timestamp = time.time()
    return int(timestamp // 86400)
