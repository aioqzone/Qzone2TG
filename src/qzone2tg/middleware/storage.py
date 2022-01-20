import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from ..utils.iterutils import find_if

logger = logging.getLogger(__name__)


class Table:
    order_on = None

    def __init__(
        self, name: str, cursor: sqlite3.Cursor, key: Dict[str, Any], pkey: str = None
    ) -> None:
        pkey = pkey or find_if(key.items(), lambda t: 'PRIMARY KEY' in t[1])[0]
        assert pkey and pkey in key
        self.name = name
        self.cursor = cursor
        self.key = key
        self.pkey = pkey

    @staticmethod
    def arglike(i):
        return "'%s'" % i.replace("'", "''") if isinstance(i, str) else \
            str(int(i)) if isinstance(i, bool) else \
            str(i)

    def createTable(self, index: list = None):
        args = ','.join(f"{k} {v}" for k, v in self.key.items())
        self.cursor.execute(f"create table if not exists {self.name} ({args});")
        if index:
            args = ','.join(index)
            self.cursor.execute(
                f"create index if not exists {self.name}_idx on {self.name} ({args});"
            )

    def __getitem__(self, i):
        self.cursor.execute(f'select * from {self.name} WHERE {self.pkey}={self.arglike(i)};')
        if (r := self.cursor.fetchone()) is None: return
        return dict(zip(self.key, r))

    def __setitem__(self, k, data: dict):
        assert all(i in self.key for i in data)
        if k in self:
            if self.pkey in data: data.pop(self.pkey)
            vals = ','.join(f"{k}={self.arglike(v)}" for k, v in data.items())
            self.cursor.execute(
                f'update {self.name} SET {vals} WHERE {self.pkey}={self.arglike(k)};'
            )
        else:
            ndata = data.copy()
            ndata[self.pkey] = k
            cols = ','.join(ndata)
            vals = ','.join(self.arglike(i) for i in ndata.values())
            self.cursor.execute(f'insert into {self.name} ({cols}) VALUES ({vals});')
        return data

    def __delitem__(self, i):
        self.cursor.execute(f'delete from {self.name} WHERE {self.pkey}={self.arglike(i)};')

    def __contains__(self, i):
        return bool(Table.__getitem__(self, i))

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
            f'{self.name} LEFT OUTER JOIN {tbl.name} USING ({self.pkey})', self.cursor, key,
            self.pkey
        )
        r.parent = self, tbl
        return r

    def __iter__(self):
        yield from self.find(order=self.order_on)


class _DBBase:
    def __init__(self, db: Union[str, sqlite3.Connection], thread_safe=False) -> None:
        if isinstance(db, sqlite3.Connection):
            self.db = db
        else:
            Path(db).parent.mkdir(parents=True, exist_ok=True)
            self.db_path = db
            self.db = sqlite3.connect(self.db_path, check_same_thread=thread_safe)
        self.cursor = self.db.cursor()


class FeedBase(_DBBase):
    def __init__(
        self,
        db: Union[str, sqlite3.Connection],
        keepdays: int = 3,
        archivedays: int = 180,
        plugins: dict = None,
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
        self._createTable(plugins or {})

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
        self.db.commit()

    def cleanFeed(self, getLikeId: Callable[[dict], Optional[dict]]):
        del_limit = int(time.time() - self.archivedays * 86400)
        self.cursor.execute(f'delete from archive WHERE abstime <= {del_limit};')
        self.db.commit()

        arch_limit = int(time.time() - self.keepdays * 86400)
        to_move = FeedBase.getFeed(self, f'abstime <= {arch_limit}')
        assert isinstance(to_move, list)
        for i in to_move:
            # move to archive
            d = getLikeId(i)
            if d:
                fid = d.pop('key')
                d['abstime'] = i['abstime']
                self.archive[fid] = d
            # remove from feed
            for v in self.plugin.values():
                del v[i['fid']]
            del self.feed[i['fid']]
            self.db.commit()

    def getFeed(self, cond_sql: str = '', plugin_name=None, order=False):
        table = self.feed * self.plugin[plugin_name] if plugin_name else self.feed
        return table.find(
            cond_sql=cond_sql,
            order='abstime' if order else None,
        )

    def setPluginData(self, plugin: str, fid: str, flush=True, **data):
        self.plugin[plugin][fid] = data
        if flush: self.db.commit()

    def close(self):
        if not self.db: return
        self.cursor.close()
        self.db.close()
        self.db: sqlite3.Connection = None

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

    def __setitem__(self, k, data: dict):
        super().__setitem__(k, data)
        self.cursor.connection.commit()

    def __delitem__(self, i):
        super().__delitem__(i)
        self.cursor.connection.commit()
