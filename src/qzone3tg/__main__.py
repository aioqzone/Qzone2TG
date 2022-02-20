import argparse
import asyncio
from pathlib import Path

from aiohttp import ClientSession
import yaml

from qzone3tg.app.interact import InteractApp
from qzone3tg.app.storage import AsyncEnginew
from qzone3tg.settings import Settings

DEFAULT_CONF = Path('config/settings.yml')
DEFAULT_SECRETS = Path('/run/secrets')


async def main(conf: Settings) -> int:
    async with ClientSession() as sess, AsyncEnginew.sqlite3(conf.bot.storage.database) as engine:
        app = InteractApp(sess, engine, conf)
        try:
            await app.run()
            return 0
        except (KeyboardInterrupt, asyncio.CancelledError):
            app.stop()
            return 0
        except SystemExit as e:
            return e.code
        except:
            app.log.error("Uncaught error in main.", exc_info=True)
            app.stop()
            return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--conf', '-c', help='配置文件路径 (*.yml, *.yaml)', type=Path, default=DEFAULT_CONF
    )
    parser.add_argument('--secrets', '-s', help='密钥目录', type=Path, default=DEFAULT_SECRETS)
    args = parser.parse_args()

    assert args.conf.exists()
    with open(args.conf) as f:
        d = yaml.safe_load(f)
    conf = Settings(**d).load_secrets(args.secrets)

    try:
        code = asyncio.run(main(conf))
    except (KeyboardInterrupt, asyncio.CancelledError):
        code = 0
    except SystemExit as e:
        code = e.code
    except:
        code = 1
    exit(code)
