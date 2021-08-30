import logging
import sqlite3
import time
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Union

from qzone.parser import QZFeedParser as Feed
from utils.iterutils import find_if

logger = logging.getLogger(__name__)
PAGE_LIMIT = 1000


def day_stamp(timestamp: float = None) -> int:
    if timestamp is None: timestamp = time.time()
    return int(timestamp // 86400)


def arglike(i):
    return f"'{i}'" if isinstance(i, str) else \
        str(int(i)) if isinstance(i, bool) else \
        str(i)


def noexcept(func):
    @wraps(func)
    def noexcept_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            logger.error('', exc_info=True, stack_info=True, stacklevel=2)

    return noexcept_wrapper


class Table:
    order_on = None

    def __init__(
        self,
        name: str,
        cursor: sqlite3.Cursor,
        key: Dict[str, Any],
        pkey: str = None
    ) -> None:
        pkey = pkey or find_if(key.items(), lambda t: 'PRIMARY KEY' in t[1])[0]
        assert pkey and pkey in key
        self.name = name
        self.cursor = cursor
        self.key = key
        self.pkey = pkey

    @noexcept
    def createTable(self, index: list = None):
        args = ','.join(f"{k} {v}" for k, v in self.key.items())
        self.cursor.execute(f"create table if not exists {self.name} ({args});")
        if index:
            args = ','.join(index)
            self.cursor.execute(
                f"create index if not exists {self.name}_idx on {self.name} ({args});"
            )

    @noexcept
    def __getitem__(self, i):
        self.cursor.execute(
            f'select * from {self.name} WHERE {self.pkey}={arglike(i)};'
        )
        if (r := self.cursor.fetchone()) is None: return
        return dict(zip(self.key, r))

    @noexcept
    def __setitem__(self, k, data: dict):
        assert all(i in self.key for i in data)
        if k in self:
            vals = ','.join(f"{k}={arglike(v)}" for k, v in data.items())
            self.cursor.execute(
                f'update {self.name} SET {vals} WHERE {self.pkey}={arglike(k)};'
            )
        else:
            ndata = data.copy()
            ndata[self.pkey] = k
            cols = ','.join(ndata)
            vals = ','.join(
                f"'{i}'" if isinstance(i, str) else str(i) for i in ndata.values()
            )
            self.cursor.execute(f'insert into {self.name} ({cols}) VALUES ({vals});')
        return data

    def __delitem__(self, i):
        self.cursor.execute(f'delete from archive WHERE {self.pkey}={arglike(i)};')

    def __contains__(self, i):
        return bool(Table.__getitem__(self, i))

    @noexcept
    def find(self, cond_sql: str = '', order=None):
        if cond_sql: cond_sql = 'WHERE ' + cond_sql
        order = f'ORDER BY {order}' if order else ''
        keys = list(self.key.keys())
        if hasattr(self, 'parent'):
            i = keys.index(self.pkey)
            keys[i] = f"{self.parent[0].name}.{keys[i]}"
        cols = ','.join(keys)

        self.cursor.execute(f'select {cols} from {self.name} {cond_sql} {order};')
        return [{k: v for k, v in zip(self.key, i)} for i in self.cursor.fetchall()]

    def __mul__(self, tbl):
        assert self.pkey == tbl.pkey
        key = self.key.copy()
        key.update(tbl.key)
        r = Table(
            f'{self.name} LEFT OUTER JOIN {tbl.name} USING ({self.pkey})', self.cursor,
            key, self.pkey
        )
        r.parent = self, tbl
        return r

    def __iter__(self):
        yield from self.find(order=self.order_on)


class _DBBase:
    def __init__(self, db: Union[str, sqlite3.Connection]) -> None:
        if isinstance(db, sqlite3.Connection):
            self.db = db
        else:
            Path(db).parent.mkdir(parents=True, exist_ok=True)
            self.db_path = db
            self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.db.cursor()


class FeedBase(_DBBase):
    def __init__(
        self,
        db: Union[str, sqlite3.Connection],
        keepdays: int = 3,
        archivedays: int = 180,
        plugins: dict = None
    ) -> None:

        super().__init__(db)
        self.keepdays = keepdays
        self.archivedays = archivedays

        self.feed = Table(
            'feed',
            self.cursor,
            {
                'fid': 'CHAR(24) PRIMARY KEY',
                'abstime': 'int NOT NULL',
                'appid': 'int NOT NULL',
                'typeid': 'int NOT NULL',
                'feedstime': 'VARCHAR NOT NULL',
                'nickname': 'VARCHAR NOT NULL',
                'uin': 'int NOT NULL',
                'html': 'VARCHAR NOT NULL',
            },
            'fid',
        )
        self.archive = Table(
            'archive',
            self.cursor,
            {
                'fid': 'CHAR(24) PRIMARY KEY',
                'abstime': 'int NOT NULL',
                'appid': 'int NOT NULL',
                'typeid': 'int NOT NULL',
                'unikey': 'VARCHAR NOT NULL',
                'curkey': 'VARCHAR NOT NULL',
            },
            'fid',
        )
        self._createTable(plugins)

    def _createTable(self, plugin_defs: dict, create_index=True):
        index = ('fid', 'abstime') if create_index else None
        self.feed.createTable(index)
        self.archive.createTable(index)
        self.plugin = {
            k: Table(k, self.cursor,
                     v.update(fid='CHAR(24) PRIMARY KEY') or v, 'fid')
            for k, v in plugin_defs.items()
        }
        for i in self.plugin.values():
            i.createTable()

    def cleanFeed(self):
        del_limit = int(time.time() - self.archivedays * 86400)
        self.cursor.execute(f'delete from archive WHERE abstime <= {del_limit};')
        self.db.commit()

        arch_limit = int(time.time() - self.keepdays * 86400)
        for i in self.getFeed(f'abstime <= {arch_limit}'):
            # move to archive
            d = i.getLikeId()
            d.update(fid=d.pop('key'), abstime=i.abstime)
            self.archive[i.fid] = d
            # remove from feed
            for v in self.plugin.values():
                del v[i.fid]
            del self.feed[i.fid]
            self.db.commit()

    def dumpFeed(self, feed: Feed, flush=True):
        args = {
            'fid': feed.fid,
            'abstime': feed.abstime,
            'appid': feed.appid,
            'typeid': feed.typeid,
            'feedstime': feed.feedstime,
            'nickname': feed.nickname,
            'uin': feed.uin,
            'html': feed.raw['html'].replace("'", '"'),
        }
        self.feed[feed.fid] = args
        if flush: self.db.commit()

    def getFeed(self, cond_sql: str = '', plugin_name=None, order=False):
        table = self.feed * self.plugin[plugin_name] if plugin_name else self.feed
        r = table.find(
            cond_sql=cond_sql,
            order='abstime' if order else None,
        )
        return r is not None and [Feed(i) for i in r]

    def setPluginData(self, plugin: str, fid: str, flush=True, **data):
        self.plugin[plugin][fid] = data
        if flush: self.db.commit()

    def saveFeeds(self, feeds):
        for i in feeds:
            self.dumpFeed(i, flush=False)
        self.db.commit()

    def close(self):
        self.cursor.close()
        self.db.close()

    def __del__(self):
        self.close()


class TokenTable(Table):
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        super().__init__(
            'token',
            cursor,
            key={
                'uin': 'INT PRIMARY KEY',
                'p_skey': 'VARCHAR NOT NULL',
                'p_uin': 'VARCHAR NOT NULL',
                'pt4_token': 'VARCHAR NOT NULL',
                'skey': 'VARCHAR NOT NULL',
            },
            pkey='uin'
        )
        self.createTable()

    def __getitem__(self, uin: int):
        d = super().__getitem__(uin)
        d['uin'] = f"o0{uin}"
        return d
