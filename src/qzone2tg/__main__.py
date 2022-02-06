import argparse
import asyncio
from pathlib import Path

from aiohttp import ClientSession
from app.interact import InteractApp
from pydantic import DirectoryPath
from pydantic import FilePath
from settings import Settings
import yaml

DEFAULT_CONF = Path('config/settings.yml')
DEFAULT_SECRETS = Path('/run/secrets')


async def main(conf: Settings):
    async with ClientSession() as sess:
        app = InteractApp(sess, conf)
        await app.run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--conf', '-c', help='配置文件路径 (*.yml, *.yaml)', type=FilePath, default=DEFAULT_CONF
    )
    parser.add_argument(
        '--secrets', '-s', help='密钥目录', type=DirectoryPath, default=DEFAULT_SECRETS
    )
    args = parser.parse_args()

    assert args.conf.exists()
    with open(args.conf) as f:
        d = yaml.safe_load(f)
    conf = Settings(**d).load_secrets(args.secrets)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(conf))
