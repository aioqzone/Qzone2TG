"""This module read user config as a global object."""

from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import (
    AnyUrl,
    BaseModel,
    BaseSettings,
    DirectoryPath,
    Field,
    FilePath,
    HttpUrl,
    SecretStr,
    validator,
)
from pydantic.env_settings import SettingsSourceCallable

__all__ = ["Settings"]


class StorageConfig(BaseModel):
    """Bot 存储配置，对应 :obj:`bot.storage <.BotConf.storage>`。Bot 将保留说说的一部分必要参数，用于验证说说是否已爬取、已发送，以及用于点赞、取消赞等.
    存储的信息不包括说说内容, 但通常能够通过存储的参数复原说说内容."""

    database: Optional[Path] = None
    """数据库地址. Bot 会在此位置建立一个 sqlite3 数据库. 如果目录不存在，会自动新建目录.
    如果传入值为 ``None``，则不建立文件数据库，而是维持一个内存数据库。"""

    keepdays: float = 30
    """一条记录要保存多长时间，以天为单位. 默认为30."""


class BotDefaultConf(BaseModel):
    """对应 :obj:`bot.default <.BotConf.default>`. Bot 的一些默认值配置。包括禁止通知、禁止链接预览等.

    .. seealso:: :external:class:`telegram.ext.Defaults`

    .. versionchanged:: 0.5.0a1

        Removed ``timeout``, added :obj:`.protect_content`
    """

    disable_notification: bool = False
    disable_web_page_preview: bool = False
    protect_content: bool = False


class PollingConf(BaseModel):
    """对应 :obj:`bot.init_args <.BotConf.init_args>`. 顾名思义，:term:`polling` 模式通过频繁地向 telegram 查询消息来确保能够响应用户的命令.
    比 :term:`webhook` 简单、要求低，适合测试使用.

    .. seealso:: :external:meth:`telegram.ext.Updater.start_polling`"""

    poll_interval: float = 0.0
    """查询间隔. 较大的间隔会导致响应不及时."""

    timeout: float = 10
    """查询超时."""

    bootstrap_retries: int = -1
    read_timeout: float = 2.0
    """Timeout when reading from telegram.

    .. versionchanged:: 0.5.0a3

        renamed to `read_timeout`
    """
    drop_pending_updates: bool = False
    """Bot 启动后不响应启动前等待的命令. """


class WebhookConf(BaseModel):
    """对应 :obj:`bot.init_args <.BotConf.init_args>`. :term:`Webhook <webhook>` 的原理是在本机启动一个小型服务器以接收 telegram api 的更新消息. 因为不必时时从 telegram 查询更新，
    :term:`webhook` 的效率更高，资源消耗更少. 用户需要保证 `!telegram api` 能够通过 :obj:`.destination` 访问到这个服务器.

    此外，由于 `!telegram api` 的限制，对 :obj:`webhook destination <.destination>` 的请求必须开启 SSL.
    因此您可能需要域名（和证书）才能使用 :term:`webhook`.

    .. seealso:: :external:meth:`telegram.ext.Updater.start_webhook`"""

    destination: HttpUrl
    """webhook url. `!telegram api` 将向此地址发送数据. 如果您配置了反向代理，可填写反向代理的转发地址.

    Example:

    - `!https://this.server.xyz:443` 如果没有额外配置，替换本机域名即可.
    - `!https://this.server.xyz:443/any/prefix/you/like` 若您配置的反向代理会将 url 转发到 :obj:`.port` 指明的端口，则填写这个 url."""

    port: int = 443
    """webhook 端口. :abbr:`PTB (Python Telgram Bot)` 会在此端口上设置一个小型的服务器用于监听请求. 用户需要保证 `!telegram api` 可以直接请求此端口，
    或经反向代理等中间环节间接访问此端口.

    受 :abbr:`PTB`:external:data:`限制 <telegram.constants.SUPPORTED_WEBHOOK_PORTS>`,
    端口只能在 443, 80, 88, 8443 中选择。
    """

    cert: Optional[FilePath] = None
    """证书. 用于开启 SSL 认证. 若您使用反向代理，则应该在反向代理服务器设置证书，此处留空即可."""

    key: Optional[FilePath] = None
    """证书私钥. 用于开启 SSL 认证. 若您使用反向代理，则应该在反向代理服务器设置证书，此处留空即可."""

    bootstrap_retries: int = 0
    drop_pending_updates: bool = False
    """Bot 启动后不响应启动前等待的命令. """
    max_connections: int = 40
    """服务器最大连接数"""
    secret_token: Optional[str] = None
    """用于确保 webhook 请求确实是您所设置的。实际上是校验每个请求头的``X-Telegram-Bot-Api-Secret-Token``字段。
    默认为 None, 不校验。

    .. versionadded:: 0.5.0a3
    """

    @validator("destination")
    def force_https(cls, v: HttpUrl):
        """webhook 地址强制启用 SSL"""
        assert v.scheme == "https", "webhook needs a https server"
        return v

    def webhook_url(self, token: SecretStr | None = None):
        """获取实际的 webhook url. `!telegram api` 实际访问的 url 是 ``destination/bot_token``.
        用户不需要考虑这一连接过程，由程序完成拼接. 用户应该注意的是，如果要使用反向代理，对 :obj:`.destination`
        路径的一切访问都应该转发."""
        if token is None:
            return SecretStr(self.destination)
        urljoin = lambda u, p: str(u) + ("" if str.endswith(u, "/") else "/") + p
        return SecretStr(urljoin(str(self.destination), token.get_secret_value()))

    @validator("port")
    def port_choice(cls, v: int):
        from telegram.constants import SUPPORTED_WEBHOOK_PORTS

        assert v in SUPPORTED_WEBHOOK_PORTS
        return v


class NetworkConf(BaseModel):
    """网络配置，对应配置文件中的 :obj:`bot.network <.BotConf.network>`. 包括代理和自定义等待时间等。"""

    proxy: Optional[AnyUrl] = Field(None, env="HTTPS_PROXY")
    """代理设置，支持 :term:`http <http_proxy>` 和 :term:`socks <socks_proxy>` 代理.
    代理将用于向 `!telegram api` 和 `!github` 发送请求. 也支持读取系统全局代理 :envvar:`HTTPS_PROXY`,
    但优先级 **低于** 配置文件提供的值。

    Example:

    - `!http://127.0.0.1:1234`
    - `!https://username:password@your.proxy.com:1234`
    - `!socks5://user:pass@host:port`

    .. versionchanged:: 0.5.0a3

        PTB v20.0 使用 httpx 作为后端，httpx 默认在（代理）服务器端解析 DNS，且 httpx 不支持 socks5h 协议。
    """

    @validator("proxy")
    def proxy_scheme(cls, v):
        """验证代理 url 协议"""
        assert v.scheme in ("http", "https", "socks", "socks5", "socks5h")
        return v

    connect_timeout: Optional[float] = 20
    """服务器向 telegram 和 Qzone 发起连接的最长耗时。单位为秒，默认为20

    .. versionadded:: 0.5.0a8

    .. versionchanged:: 0.5.1a1
        此参数也控制与 Qzone 连接的超时。
    """


class BotConf(BaseModel):
    """对应配置文件中的 :obj:`bot <.Settings.bot>` 项。"""

    admin: int
    """管理员用户ID，唯一指明管理员. bot 只响应管理员的指令. """

    token: Optional[SecretStr] = None
    network: NetworkConf = NetworkConf()  # type: ignore
    """网络配置。包括代理和等待时间自定义优化。"""

    storage: StorageConfig = StorageConfig(keepdays=1)
    """存储配置。Bot 将保留说说的一部分必要参数，用于点赞/取消赞/转发/评论等. 存储的信息不包括说说内容.
    默认只在内存中建立 :program:`sqlite3` 数据库。"""

    default: BotDefaultConf = BotDefaultConf()
    """Bot 的默认行为配置。包括禁止通知、禁止链接预览等."""

    init_args: Union[WebhookConf, PollingConf] = PollingConf()
    """Bot 的启动配置. 根据启动配置的类型不同, bot 会以不同的模式启动.

    * 按照 :class:`.PollingConf` 填写，对应 :term:`polling` 模式（默认）；
    * 按照 :class:`.WebhookConf` 填写，对应 :term:`webhook` 模式。"""

    auto_start: bool = False
    """是否在程序启动后自动运行一次更新（``/start``）。默认为 ``False``.

    .. versionadded:: 0.2.7.dev2
    """


class QzoneConf(BaseModel):
    """对应配置文件中的 ``qzone`` 项。包含要登陆的QQ账户信息和爬虫相关的设置。"""

    uin: int = Field(alias="qq")
    """QQ账号"""

    password: Optional[SecretStr] = None
    qr_strategy: str = "allow"
    """二维码策略. 枚举类型，可选值为 ``force``, ``prefer``, ``allow``, ``forbid``

    - ``force``：强制二维码登录，不使用密码登录. **如果环境中没有安装 :program:`<node>`，则仅此模式可用**.
    - ``prefer``：二维码优先于密码登录. 当二维码登陆失败（包括未得到用户响应时）尝试密码登录.
    - ``allow``：密码优先于二维码登录. 当密码登陆失败（通常是在新设备上登录触发了保护）时使用二维码登录. **推荐普通用户使用**.
    - ``forbid``：禁止二维码登录. 通常用于自动测试."""
    min_qr_interval: float = 7200
    """最短的二维码登录时间间隔，单位为秒，默认7200（两小时）

    .. versionadded:: 0.5.0a7
    """
    min_up_interval: float = 3600
    """密码登录发生错误后，距下次密码登录的最短时间间隔，单位为秒，默认3600

    .. versionadded:: 0.5.0a7

    .. versionchanged:: 0.6.5

        密码登录成功不会触发暂停机制。
    """
    vcode_timeout: float = 30
    """等待动态验证码的超时时间，单位秒，默认30。

    .. versionadded:: 0.4.1a1
    """

    dayspac: float = 3
    """最多爬取从现在起多长时间内的说说，以天为单位. 默认为3."""
    block: Optional[list[int]] = None
    """黑名单 qq. 列表中的用户发布的任何内容会被直接丢弃."""
    block_self: bool = True
    """是否舍弃当前登录账号发布的内容. 等同于在 :obj:`.block` 中加入当前 :obj:`.uin`"""


class LogConf(BaseModel):
    """日志配置，对应配置文件中的 ``log`` 项。

    .. seealso:: :external+python:mod:`logging 模块 <logging>`
    """

    level: Optional[str] = "INFO"
    """日志等级。``NOTSET`` < ``DEBUG`` < ``INFO`` < ``WARNING`` < ``ERROR`` < ``FATAL``."""
    format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    """日志格式。

    .. seealso::

        * :external+python:class:`logging.Formatter`
        * `LogRecord attributes <https://docs.python.org/3/library/logging.html#logrecord-attributes>`_
    """
    style: Literal["%", "{", "$"] = "%"
    """
    :obj:`.format` 所使用的模板格式。可选值为 ``%``, ``{``, ``$``.
    分别对应 `!%(message)`, `!{message}`, `!$message`.

    .. versionadded:: 0.3.2
    """
    datefmt: Optional[str] = None
    """
    .. seealso::

        :external+python:obj:`time.strftime`
    """
    conf: Optional[FilePath] = None
    r"""日志配置文件，指定此项将导致其他配置被忽略，因为您可以在 `日志配置文件`_ 中指定更详细更复杂的配置。

    .. versionchanged:: 0.3.2

        更改为 yml 格式而非配置文件格式 (\*.ini, \*.conf)

    .. seealso::

        * `日志配置文件`_
        * `Configuration dictionary schema <https://docs.python.org/3/library/logging.config.html#logging-config-dictschema>`_
    """

    debug_status_interval: float = 0
    """*用于开发人员检查程序状态*。每隔多长时间以 `!debug` 模式运行一次 :command:`/status` 指令。小于等于0时不发送，默认为0。

    .. versionadded:: 0.2.8.dev1
    """


class UserSecrets(BaseSettings):
    """**直接写在配置文件中的明文密码/密钥不会被读取**。
    用户可以通过 :term:`docker secrets` 或环境变量来传递密码/密钥。
    """

    password: Optional[SecretStr] = Field(default=None, env=["TEST_PASSWORD", "password"])
    """QQ密码，支持以下两种输入：

    * 名为 ``password`` 的 :term:`docker secrets`
    * 名为 :envvar:`TEST_PASSWORD` 或 :envvar:`password` 的环境变量
    """

    token: SecretStr = Field(env=["TEST_TOKEN", "token"])
    """TG 机器人的密钥(bot token)，支持以下两种输入：

    * 名为 ``token`` 的 :term:`docker secrets`
    * 名为 :envvar:`TEST_TOKEN` 或 :envvar:`token` 的环境变量"""

    class Config:
        secrets_dir = "/run/secrets"

        @classmethod
        def customise_sources(
            cls,
            init_settings: SettingsSourceCallable,
            env_settings: SettingsSourceCallable,
            file_secret_settings: SettingsSourceCallable,
        ) -> tuple[SettingsSourceCallable, ...]:
            return env_settings, file_secret_settings


class Settings(BaseSettings):
    """:program:`Qzone3TG` 的配置文件。目前包括三大项：:class:`bot <.BotConf>`,
    :class:`log <.LogConf>`, :class:`qzone <.QzoneConf>`."""

    log: LogConf = LogConf()
    """日志配置: :class:`.LogConf`, 对应 :doc:`log <log>` 项"""

    qzone: QzoneConf
    """爬虫配置: :class:`.QzoneConf`, 对应 :doc:`qzone <qzone>` 项"""

    bot: BotConf
    """bot配置: :class:`.BotConf`, 对应 :doc:`bot <bot>` 项"""

    def load_secrets(self, secrets_dir: Optional[DirectoryPath] = None):
        secrets = UserSecrets(_secrets_dir=secrets_dir and secrets_dir.as_posix())  # type: ignore
        self.qzone.password = secrets.password
        self.bot.token = secrets.token
        return self

    class Config:
        env_nested_delimiter = "."
