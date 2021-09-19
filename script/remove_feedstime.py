# 2.0.0rc3 removes 'feedstime' column to avoid time representation mistake.
# Run this SQL script to make your current database compatible with the new version.

# 2.0.0rc3 移除了'feedstime'以避免时间表示问题.
# 此脚本将更新您的数据库以保证数据库与新版本的兼容性.

import sqlite3, argparse
from pathlib import Path
from typing import Any, Dict


def arglike(i):
    return f"'{i}'" if isinstance(i, str) else \
        str(int(i)) if isinstance(i, bool) else \
        str(i)


class Table:
    """a simplized verion of middleware.storage.Table"""
    order_on = None

    def __init__(
        self, name: str, cursor: sqlite3.Cursor, key: Dict[str, Any], pkey: str
    ) -> None:
        assert pkey and pkey in key
        self.name = name
        self.cursor = cursor
        self.key = key
        self.pkey = pkey

    def createTable(self, index: list = None):
        args = ','.join(f"{k} {v}" for k, v in self.key.items())
        self.cursor.execute(f"create table if not exists {self.name} ({args});")
        if index:
            args = ','.join(index)
            self.cursor.execute(
                f"create index if not exists {self.name}_idx on {self.name} ({args});"
            )

    def __getitem__(self, i):
        self.cursor.execute(
            f'select * from {self.name} WHERE {self.pkey}={arglike(i)};'
        )
        if (r := self.cursor.fetchone()) is None: return
        return dict(zip(self.key, r))

    def __setitem__(self, k, data: dict):
        assert all(i in self.key for i in data)
        if k in self:
            if self.pkey in data: data.pop(self.pkey)
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

    def __contains__(self, i):
        return bool(Table.__getitem__(self, i))

    def find(self, cond_sql: str = '', order=None):
        if cond_sql: cond_sql = 'WHERE ' + cond_sql
        order = f'ORDER BY {order}' if order else ''
        keys = list(self.key.keys())
        cols = ','.join(keys)

        self.cursor.execute(f'select {cols} from {self.name} {cond_sql} {order};')
        return [{k: v for k, v in zip(self.key, i)} for i in self.cursor.fetchall()]

    def __iter__(self):
        yield from self.find(order=self.order_on)


def main(db_file: Path, create_index=True):
    with sqlite3.connect(db_file.as_posix()) as db:
        cursor = db.cursor()
        index = ('fid', 'abstime') if create_index else None
        coldef = {
            'fid': 'CHAR(24) PRIMARY KEY',
            'abstime': 'int NOT NULL',
            'appid': 'int NOT NULL',
            'typeid': 'int NOT NULL',
            'feedstime': 'VARCHAR NOT NULL',
            'nickname': 'VARCHAR NOT NULL',
            'uin': 'int NOT NULL',
            'html': 'VARCHAR NOT NULL',
        }
        prev = Table('feed', cursor, coldef.copy(), 'fid')
        coldef.pop('feedstime')
        new = Table('feed', cursor, coldef, 'fid')
        prev.createTable()

        dall = [i for i in prev]
        print(f'Read {len(dall)} rows.')
        print('Transaction started.')

        cursor.execute('DROP TABLE feed;')
        new.createTable(index)
        for i in dall:
            i.pop('feedstime')
            i['html'] = i['html'].replace("'", "''")
            new[i['fid']] = i
        db.commit()
        print('Transaction completed.')


if __name__ == '__main__':
    psr = argparse.ArgumentParser()
    psr.add_argument('-i', '--input', help='Maybe data/<uin>.db', default=None)
    arg = psr.parse_args()

    fpath = arg.input
    if fpath is None:
        in_data = filter(lambda i: i.suffix == '.db', Path('data').iterdir())
        in_data = tuple(in_data)
        if len(in_data) == 1: fpath = in_data[0]
        else:
            print(
                "You've got multiple database inside `data`. "
                "You need to specify the *.db file explicitly with `-i`"
            )
            psr.print_help()
            exit(1)
    else:
        fpath = Path(fpath)
    main(fpath)
