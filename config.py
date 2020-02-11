import json, logging
import getpass

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(name)s:\t%(message)s',
    datefmt='%Y %b %d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

d = {}
with open("config.json", "r") as f: d = json.load(f)
logger.info("config loaded")

bot = d.pop("bot")
qzone = d.pop("qzone")
feed = d.pop('feed')
del d