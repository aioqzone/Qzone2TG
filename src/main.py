import base64
import getpass
import logging
from TgFrontend.tg import PollingBot

import yaml

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(name)s:\t%(message)s',
    datefmt='%Y %b %d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger("Main")

d = {}
with open("config.yaml") as f: d = yaml.load(f)
logger.info("config loaded")

bot = d.get("bot")
qzone = d.get("qzone")
feed = d.get('feed')

if 'qq' in qzone:
    print('QQ to login: %s' % qzone['qq'])
else:
    qzone['qq'] = input('QQ: ')

if "password" in qzone: 
    qzone["password"] = base64.b64decode(qzone["password"].encode('utf8')).decode('utf8')
else:
    pwd: str = getpass.getpass()
    if qzone.get('savepwd', True): 
        qzone["password"] = base64.b64encode(pwd.encode('utf8')).decode('utf8')
        with open("config.yaml", 'w') as f: yaml.dump(d, f)
    qzone["password"] = pwd

del d, pwd

PollingBot(bot["token"]).start()
