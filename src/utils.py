import base64

def pwdTransform(pwd):
    return base64.b64encode(pwd.encode('utf8')).decode('utf8')

def pwdTransBack(pwd):
    return base64.b64decode(pwd.encode('utf8')).decode('utf8')