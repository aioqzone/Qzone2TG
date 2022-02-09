"""This module read user config as a global object."""

from pathlib import Path
from typing import Optional, Union

from pydantic import AnyUrl
from pydantic import BaseModel
from pydantic import BaseSettings
from pydantic import DirectoryPath
from pydantic import Field
from pydantic import FilePath
from pydantic import HttpUrl
from pydantic import SecretStr
from pydantic import validator

__all__ = ['Settings']


class StorageConfig(BaseModel):
    """Bot 存储配置。Bot 将保留说说的一部分必要参数，用于验证说说是否已爬取、已发送，以及用于点赞、取消赞等.
    存储的信息不包括说说内容, 但通常能够通过存储的参数复原说说内容."""

    database: Optional[Path] = None
    """数据库地址. Bot 会在此位置建立一个 sqlite3 数据库. 如果目录不存在，会自动新建目录."""

    keepdays: int = 180
    """一条记录要保存多少天."""


class BotDefaultConf(BaseModel):
    """Bot 的一些默认值配置。包括禁止通知、禁止链接预览等.

    See: :external:class:`telegram.ext.Defaults`"""

    disable_notification: Optional[bool] = None
    disable_web_page_preview: Optional[bool] = None
    timeout: Optional[float] = None    # read timeout from the server


class PollingConf(BaseModel):
    """顾名思义，Polling 模式通过频繁地向 telegram 查询消息来确保能够响应用户的命令.
    比 webhook 简单、要求低，适合测试使用.

    See: :external:meth:`telegram.ext.Updater.start_polling`"""

    poll_interval: float = 0.0
    """查询间隔. 较大的间隔会导致响应不及时."""

    timeout: float = 10
    """查询超时."""

    bootstrap_retries: int = -1
    read_latency: float = 2.0
    drop_pending_updates: bool = False
    """Bot 启动后不响应启动前等待的命令. """


class WebhookConf(BaseModel):
    """Webhook 的原理是在本机启动一个小型服务器以接收 telegram api 的更新消息. 因为不必时时从 telegram 查询更新，
    webhook 的效率更高，资源消耗更少. 用户需要保证 telegram api 能够通过 `destination` 访问到这个服务器.

    此外，由于 telegram api 的限制，对 webhook destination 的请求必须开启 SSL. 因此您可能需要域名（和证书）才能使用 webhook.

    See: :external:meth:`telegram.ext.Updater.start_webhook`"""

    destination: HttpUrl
    """webhook url. telegram api 将向此地址发送数据. 如果您配置了反向代理，可填写反向代理的转发地址.

    Example:

    - `https://this.server.xyz:443` 如果没有额外配置，替换本机域名即可.
    - `https://this.server.xyz:443/any/prefix/you/like` 若您配置的反向代理会将 url 转发到 `port` 指明的端口，则填写这个 url."""

    port: int = 443
    """webhook 端口. PTB 会在此端口上设置一个小型的服务器用于监听请求. 用户需要保证 telegram api 可以直接请求此端口，
    或经反向代理等中间环节间接访问此端口."""

    cert: Optional[FilePath] = None
    """证书. 用于开启 SSL 认证. 若您使用反向代理，则应该在反向代理服务器设置证书，此处留空即可."""

    key: Optional[FilePath] = None
    """证书私钥. 用于开启 SSL 认证. 若您使用反向代理，则应该在反向代理服务器设置证书，此处留空即可."""

    bootstrap_retries: int = 0
    drop_pending_updates: bool = False
    """Bot 启动后不响应启动前等待的命令. """
    max_connections: int = 40
    """服务器最大连接数"""
    @validator('destination')
    def force_https(cls, v):
        """webhook 地址强制启用 SSL"""
        assert v.destination.scheme == 'https', "webhook needs a https server"

    def webhook_url(self, token: SecretStr = None):
        """获取实际的 webhook url. telegram api 实际访问的 url 是 destination/bot_token.
        用户不需要考虑这一连接过程，由程序完成拼接. 用户应该注意的是，如果使用反向代理，对 `destination`
        路径的一切访问都应该转发."""
        if token is None: return SecretStr(self.destination)
        from urllib.parse import urljoin
        return SecretStr(urljoin(str(self.destination), token.get_secret_value()))


class NetworkConf(BaseModel):
    """网络配置。包括代理和等待时间自定义优化。"""

    proxy: Optional[AnyUrl] = Field(None, env='HTTPS_PROXY')    # support http(s); socks(5(h)).
    """代理设置，支持 http 和 socks 代理. 代理将用于向 `telegram api` 和 `github` 发送请求.

    Example:

    - `http://127.0.0.1:1234`
    - `https://username:password@your.proxy.com:1234`
    - `socks5://localhost:7890`
    - `socks5h://username:password@your.proxy.com:7890`
    """
    @validator('proxy')
    def proxy_scheme(cls, v):
        """验证代理 url 协议"""
        assert v.scheme in ('http', 'https', 'socks', 'socks5', 'socks5h')
        return v


class BotConf(BaseModel):
    admin: int
    """管理员用户ID，唯一指明管理员. bot 只响应管理员的指令. """

    token: Optional[SecretStr] = None
    network: NetworkConf = NetworkConf()    # type: ignore
    """网络配置。包括代理和等待时间自定义优化。:class:`.NetworkConf`"""

    storage: StorageConfig = StorageConfig()
    """存储配置。Bot 将保留说说的一部分必要参数，用于点赞/取消赞/转发/评论等. 存储的信息不包括说说内容.
    默认只在内存中建立 sqlite3 数据库。"""

    default: BotDefaultConf = BotDefaultConf()
    """Bot 的默认行为配置。包括禁止通知、禁止链接预览等."""

    init_args: Union[PollingConf, WebhookConf] = PollingConf()
    """Bot 的启动配置. 根据启动配置的类型不同, bot 会以不同的模式启动.
    两种类型 :class:`.PollingConf`, :class:`.WebhookConf` 分别对应 polling 模式和 webhook 模式。"""

    reload_on_start: bool = False
    """/start 命令是否忽略已转发的内容. 即，此开关为 True 时，
    Bot 不会检查说说是否曾经转发过，而是将 :meth:`.QzoneConf.dayspac` 天内的所有说说重新转发。"""


class QzoneConf(BaseModel):
    """对应配置文件中的 `qzone` 项。包含要登陆的QQ账户信息和爬虫相关的设置。"""

    uin: int = Field(alias='qq')
    """QQ账号"""

    password: Optional[SecretStr] = None
    qr_strategy: str = 'prefer'
    """二维码策略. 枚举类型，可选值为 `force`, `prefer`, `allow`, `forbid`

    - `force`：强制二维码登录，不使用密码登录. 如果您没有安装 NodeJs，则仅此模式可用.
    - `prefer`：二维码优先于密码登录. 当二维码登陆失败（包括未得到用户响应时）尝试密码登录.
    - `allow`：密码优先于二维码登录. 当密码登陆失败（通常是在新设备上登录触发了保护）时使用二维码登录. **推荐普通用户使用**.
    - `forbid`：禁止二维码登录. 通常用于自动测试."""

    dayspac: int = 3
    """最多爬取从现在起几天内的说说. 默认为三天."""
    @validator('qr_strategy')
    def must_be_enum(cls, v):
        """确保输入的 `qr_strategy` 是四个枚举值之一."""
        assert v in ('force', 'prefer', 'allow', 'forbid')
        return v


class LogConf(BaseModel):
    """日志配置，支持配置文件."""

    level: Optional[str] = 'INFO'
    format: Optional[str] = None
    datefmt: Optional[str] = None
    conf: Optional[FilePath] = None


class UserSecrets(BaseSettings):
    """专门管理用户密码/密钥的配置。依赖于 `pydnatic` 对 secrets 的支持。用户可以通过 `docker secrets`
    或通过环境变量来传递密码/密钥。"""
    password: Optional[SecretStr] = None    # password
    """QQ 密码"""

    token: SecretStr
    """TG 机器人的 `bot token`"""
    class Config:
        env_prefix = "TEST_"
        secrets_dir = '/run/secrets'


class Settings(BaseSettings):
    """`Qzone3TG` 的配置文件。分为两部分：`Qzone` 配置 和 `TG` 配置. 除此之外还包括日志配置等杂项.
    """
    log: LogConf = LogConf()
    """日志配置: :class:`.LogConf`"""

    qzone: QzoneConf
    """爬虫配置: :class:`.QzoneConf`"""

    bot: BotConf
    """bot配置: :class:`.BotConf`"""
    def load_secrets(self, secrets_dir: DirectoryPath):
        secrets = UserSecrets(_secrets_dir=secrets_dir.as_posix())    # type: ignore
        self.qzone.password = secrets.password
        self.bot.token = secrets.token
        return self