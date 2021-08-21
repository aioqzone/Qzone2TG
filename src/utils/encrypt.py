import base64
import random


def _randstr(l: int):
    return ''.join(chr(random.randint(97, 122)) for _ in range(l))


def pwdTransform(pwd: str, prefex='$', length=63):
    l = random.randint(0, (a := length - len(pwd) - 2))
    r = _randstr(a - l)
    l = _randstr(l)
    pwd = f"{l} {pwd} {r}"
    return prefex + base64.b64encode(pwd.encode('utf8')).decode('utf8')


def pwdTransBack(pwd: str, prefex='$'):
    if pwd.startswith(prefex):
        pwd = base64.b64decode(pwd.encode('utf8')).decode('utf8')
        pwd = pwd[pwd.find(' ') + 1:]
        return pwd[:pwd.find(' ')]
    else:
        return pwd
