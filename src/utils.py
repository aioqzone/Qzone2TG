import base64
from demjson import undefined

def pwdTransform(pwd):
    return base64.b64encode(pwd.encode('utf8')).decode('utf8')

def pwdTransBack(pwd):
    return base64.b64decode(pwd.encode('utf8')).decode('utf8')

def undefined2None(dic: dict):
    for k, v in {dict: lambda d: dict.items(d), list: enumerate}[type(dic)](dic):
        if v is undefined: dic[k] = None
        elif isinstance(v, dict): undefined2None(v)
        elif isinstance(v, list): undefined2None(v)
    return dic