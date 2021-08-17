__all__ = ['json_loads']

class ValueBuf:
    __slots__ = ('_v', )

    def __init__(self) -> None:
        self._v = []

    def reduce(self):
        s = ''.join(self._v)
        self._v.clear()
        if s in (b := {'true': True, 'false': False, 'undefined': None}):
            return b[s]
        if s.isdecimal():
            return int(s)
        if '_' in s: return s
        try:
            return float(s)
        except ValueError:
            return s

    def __add__(self, c):
        assert isinstance(c, str)
        self._v.append(c)
        return self

    def __bool__(self):
        return bool(self._v)

    def __repr__(self) -> str:
        return repr(self._v)


class IrregulateJsonParser:
    escape = ('/', )

    def __init__(self) -> None:
        self._dlevel = 0
        self._llevel = 0

    def loads(self, s: str):
        s = enumerate(s)
        if next(s)[1] == '{':
            r = self._dict(s)
            assert self._dlevel == 0
            assert self._llevel == 0
            for i, c in s:
                if c.isprintable() and not c.isspace():
                    raise SyntaxError(
                        'global: json should match {...}, but something is attached after the last }'
                    )
            return r
        raise SyntaxError('global: json should match {...}, but no { is detected')

    def _dict(self, s: iter) -> dict:
        self._dlevel += 1
        buf = ValueBuf()
        kbuf = None
        key = True
        str_only = False
        reduced = False
        d = {}
        for i, c in s:
            if c == '{':
                if key: raise SyntaxError('dict key: dict cannot be key.')
                d[kbuf] = self._dict(s)
                reduced = True
            elif c == '[':
                if key: raise SyntaxError('dict key: list cannot be key.')
                d[kbuf] = self._list(s)
                reduced = True
            elif c in ['"', "'"]:
                if buf and not str_only:
                    raise SyntaxError(f'str: something before {c} without seperate')
                buf += self._str(s, c)
                str_only = True
            elif c == '}':
                if not key and not reduced:
                    d[kbuf] = buf.reduce()
                self._dlevel -= 1
                return d
            elif c == ']':
                raise SyntaxError('dict: Expect } as dict end, but got ] instead.')
            elif c == ':':
                if not key:
                    raise SyntaxError('dict value: Expect , or } but got : instead')
                key = False
                str_only = False
                kbuf = buf.reduce()
            elif c == ',':
                if key: raise SyntaxError('dict key: Expect : but got , instead')
                key = True
                str_only = False
                if not reduced: d[kbuf] = buf.reduce()
                else: reduced = False
                kbuf = None
            elif c.isprintable() and not c.isspace():
                if str_only:
                    raise SyntaxError(
                        'str: something attached after str without seperate'
                    )
                buf += c
        raise SyntaxError("dict: Expect } as dict end, but no } appear until EOF.")

    def _str(self, s: iter, S: str):
        buf = []
        for i, c in s:
            if c == '\\':
                _, n = next(s)
                buf.append(n if n in self.escape else f"\\{n}")
            elif c == S:
                return ''.join(buf)
            else:
                buf.append(c)
        raise SyntaxError(f'Expect {S} as string end, but no {S} appear until EOF.')

    def _list(self, s: iter) -> list:
        self._llevel += 1
        l = []
        str_only = False
        reduced = False
        buf = ValueBuf()

        for i, c in s:
            if c == '{':
                l.append(self._dict(s))
                reduced = True
            elif c == '[':
                l.append(self._list(s))
                reduced = True
            elif c == ']':
                if not reduced and buf: l.append(buf.reduce())
                self._llevel -= 1
                return l
            elif c == '}':
                raise SyntaxError('list: Expect ] as list end, but got } instead.')
            elif c in ['"', "'"]:
                if buf and not str_only:
                    raise SyntaxError(f'str: something before {c} without seperate')
                buf += self._str(s, c)
                str_only = True
            elif c == ':':
                raise SyntaxError('list: Unexpected : in list')
            elif c == ',':
                str_only = False
                if not reduced: l.append(buf.reduce())
                else: reduced = False
            elif c.isprintable():
                if str_only:
                    raise SyntaxError(
                        'str: something attached after str without seperate'
                    )
                buf += c
        raise SyntaxError("list: Expect ] as list end, but no ] appear until EOF.")


def json_loads(s):
    return IrregulateJsonParser().loads(s)
