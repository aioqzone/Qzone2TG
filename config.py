import json, logging
import getpass, base64

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(name)s:\t%(message)s',
    datefmt='%Y %b %d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

d = {}
with open("config.json", "r") as f: d = json.load(f)
logger.info("config loaded")

bot = d.get("bot")
qzone = d.get("qzone")
feed = d.get('feed')

if "password" in qzone: 
    qzone["password"] = base64.b64decode(qzone["password"].encode('utf8')).decode('utf8')
else:
    pwd: str = getpass.getpass()
    qzone["password"] = base64.b64encode(pwd.encode('utf8')).decode('utf8')
    with open("config.json", 'w') as f: json.dump(d, f, indent=4)
    qzone["password"] = pwd

del d
