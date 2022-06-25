import argparse
import asyncio
from pathlib import Path

import yaml
from httpx import AsyncClient
from pydantic import ValidationError
from qqqr.ssl import ssl_context
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncEngineFactory

from qzone3tg.app.interact import InteractApp
from qzone3tg.settings import Settings

DEFAULT_CONF = Path("config/settings.yml")
DEFAULT_SECRETS = Path("/run/secrets")


async def main(conf: Settings) -> int:
    async with (
        AsyncClient(verify=ssl_context()) as client,
        AsyncEngineFactory.sqlite3(conf.bot.storage.database) as engine,
    ):
        # this client is used for QzoneApi/BotFetcher. So set the ssl context, unset the proxy.
        # UA will be set by qqqr once this client is used for login.
        # telegram proxy will be set by App._request_args, through PTB updater.
        app = InteractApp(ClientAdapter(client), engine, conf)
        try:
            await app.run()
            return 0
        except (KeyboardInterrupt, asyncio.CancelledError):
            return 0
        except SystemExit as e:
            return e.code
        except:
            app.log.error("Uncaught error in main.", exc_info=True)
            return 1
        finally:
            app.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conf", "-c", help="配置文件路径 (*.yml, *.yaml)", type=Path, default=DEFAULT_CONF
    )
    parser.add_argument("--secrets", "-s", help="密钥目录", type=Path, default=DEFAULT_SECRETS)
    parser.add_argument("--version", "-v", help="打印版本", action="store_true")
    args = parser.parse_args()

    if args.version:
        from qzone3tg import VERSION

        print(VERSION)
        exit(0)

    d = {}
    if args.conf.exists():
        with open(args.conf) as f:
            d = yaml.safe_load(f)
    # support for a entire env-settings

    try:
        conf = Settings(**d).load_secrets(args.secrets)
    except ValidationError as e:
        if args.conf.exists():
            raise e
        raise FileNotFoundError(args.conf) from e

    exit(asyncio.run(main(conf)))
