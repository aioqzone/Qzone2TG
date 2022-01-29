"""This module read user config as a global object."""

from typing import Optional, Union

from pydantic import (AnyUrl, BaseModel, BaseSettings, DirectoryPath, FilePath,
                      HttpUrl, SecretStr, validator)

__all__ = ['Settings']


class StorageConfig(BaseModel):
    database: str
    keepdays: int = 180    # how many days should a record be kept.


class BotDefaultConf(BaseModel):
    disable_notification: Optional[bool] = None
    disable_web_page_preview: Optional[bool] = None
    timeout: Optional[float] = None    # read timeout from the server


class PollingConf(BaseModel):
    poll_interval: float = 0.0
    timeout: float = 10
    bootstrap_retries: int = -1
    read_latency: float = 2.0
    drop_pending_updates: bool = False


class WebhookConf(BaseModel):
    destination: HttpUrl    # webhook destination
    port: int = 80
    cert: Optional[FilePath] = None
    key: Optional[FilePath] = None

    bootstrap_retries: int = 0
    drop_pending_updates: bool = False
    max_connections: int = 40

    @validator('destination')
    def force_https(cls, v):
        assert v.destination.scheme == 'https', "webhook needs a https server"

    def webhook_url(self, token: SecretStr = None):
        if token is None: return SecretStr(self.destination)
        from urllib.parse import urljoin
        return SecretStr(urljoin(str(self.destination), token.get_secret_value()))


class NetworkConf(BaseModel):
    proxy: Optional[AnyUrl] = None    # support http(s); socks(5(h)).

    @validator('proxy')
    def proxy_scheme(cls, v):
        assert v.scheme in ('http', 'https', 'socks', 'socks5', 'socks5h')
        return v


class BotConf(BaseModel):
    admin: Union[str, int]    # Bot will interact only with this user
    token: Optional[SecretStr] = None    # The only token to identify a bot
    network: NetworkConf = NetworkConf()

    storage: Optional[StorageConfig] = None
    default: BotDefaultConf = BotDefaultConf()

    init_args: Union[PollingConf, WebhookConf] = PollingConf()


class QzoneConf(BaseModel):
    uin: int    # aka. qq
    password: Optional[SecretStr] = None    # password
    qr_strategy: str = 'prefer'

    @validator('qr_strategy')
    def strategy_set(cls, v):
        assert v in ('force', 'prefer', 'allow', 'forbid')
        return v


class LogConf(BaseModel):
    level: Optional[str] = 'INFO'
    format: Optional[str] = None
    datefmt: Optional[str] = None
    conf: Optional[FilePath] = None


class UserSecrets(BaseSettings):
    password: Optional[SecretStr] = None    # password
    token: SecretStr    # The only token to identify a bot

    class Config:
        env_prefix = "TEST_"
        secrets_dir = '/run/secrets'


class Settings(BaseSettings):
    log: LogConf = LogConf()
    qzone: QzoneConf
    bot: BotConf

    def load_secrets(self, secrets_dir: DirectoryPath):
        secrets = UserSecrets(_secrets_dir=secrets_dir.as_posix())    # type: ignore
        self.qzone.password = secrets.password
        self.bot.token = secrets.token
        return self
