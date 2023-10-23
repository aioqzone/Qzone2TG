import argparse
import asyncio
from pathlib import Path

import yaml
from pydantic import ValidationError
from qqqr.utils.net import ClientAdapter

from qzone3tg.app.interact import InteractApp
from qzone3tg.settings import Settings

DEFAULT_CONF = Path("config/settings.yml")
DEFAULT_SECRETS = Path("/run/secrets")


async def main(conf: Settings) -> int:
    async with InteractApp(conf) as app:
        try:
            await app.run()
            return 0
        except (KeyboardInterrupt, asyncio.CancelledError):
            return 0
        except SystemExit as e:
            app.log.fatal(f"Uncaught error in main: {e.code}")
            if isinstance(e.code, int):
                return e.code
            return 1
        except:
            app.log.fatal("Uncaught error in main.", exc_info=True)
            return 1
        finally:
            await app.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conf", "-c", help="配置文件路径 (*.yml, *.yaml)", type=Path, default=DEFAULT_CONF
    )
    parser.add_argument("--secrets", "-s", help="密钥目录", type=Path, default=DEFAULT_SECRETS)
    args = parser.parse_args()

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
