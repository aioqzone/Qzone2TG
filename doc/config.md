## 配置文件说明

> Tips: `ctrl+F`页内搜索`FutureWarning`以确保您的配置格式保持最新:D

### 配置格式

本项目采用yaml存储和书写配置.

~~~ yaml
log: 
qzone: 
feed: 
bot: 
~~~

- log: [logConfig](#日志), 控制日志格式和日志等级
- qzone: [qzoneConfig](#爬虫), 爬虫参数和行为
- feed: [feedConfig](#数据库), 指定数据保存期限
- bot: [botConfig](#机器人), TG机器人配置, 触发时间, webhook等

### 日志

  键名: `log`

  ~~~ yaml
  level: info
  # format: "[%(levelname)s] %(asctime)s %(name)s: %(message)s"
  # conf: misc/config.ini
  ~~~

> `level`: string (enum)

  日志等级. 默认`INFO`
  - `DEBUG`: 适用于开发人员. 捕捉开发者留意到的bug时或许有用)
  - `INFO`: 默认. 输出程序的大多数行为, 报告任何错误.
  - `WARNING`: 屏蔽程序的行为报告, 仅报告值得注意的问题和错误.
  - `ERROR`: 仅报告错误
  - `FATAL`: 仅当发生致命错误时报告
  - `CRITICAL`: 同上
  - `NOTSET`: 不显示任何日志

--- 
  > `format`: string

  日志格式. _可选_. 默认为`"[%(levelname)s] %(asctime)s %(name)s: %(message)s"`

  参见`logging`模块的格式配置. 

--- 
  > `conf`: string (path)

  日志配置文件. _可选_ 使用此ini文件所定义的日志行为、格式. 此文件的书写规范参考`logging`模块的`fileConfig`.

### 爬虫

  键: `qzone`

  ~~~ yaml
  # UA: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36 Edg/92.0.902.62
  # fetch_times: 12
  qq: 123456789
  # savepwd: False
  # password: dontsavepwdondisk
  qr_strategy: prefer
  ~~~

  > `UA`: string

  User-Agent. _可选_. 理论上 __重要__. 程序内部自带PC UA, 但并不一定能时刻保持更新. 用户可以自行更换.

--- 
  > `fetch_times`: integer

  爬取说说时允许重试的次数. _可选_. 目前, 此参数只用于发生`-10001`错误时重试. 此参数有可能在未来移除. 

--- 
  > `qq`: integer

  __重要__. 在交互模式下, 未指定此参数时程序会等待用户输入. 禁用交互模式时, 未指定此参数会触发错误.

--- 
  > `password`: string

  密码. __cli only__. 

  __FutureWarning & [安全策略]__ 自`2.0.0b5`起, 本项目采用[keyring][keyring]作为密码存储方式. 原有的配置文件存储即刻停止支持. 由于安全原因, 用户需要自行删除配置文件中的`password`和`savepwd`字段. 对于使用交互模式的用户而言, 启动程序的逻辑没有变化, 程序将提示您输入密码, 并由`keyring`"记住密码". 

  Tips: 从命令行传入`password`仍然支持. 但请注意, 此功能的保留应仅用于开发用途. 非交互模式的用户的正确做法是在程序运行前执行

  ~~~ shell
  keyring qzone2tg <qq> <password>
  ~~~

  [keyring]: https://github.com/jaraco/keyring "keyring"

--- 
  > `qr_strategy`: string (enum)

  二维码策略. _可选_. 默认为`prefer`.
  - `force`: 强制使用二维码登录. 当密码为空时, `prefer`和`allow`会切换至此策略.
  - `prefer`: 倾向于使用二维码. 二维码登录失败后, 会尝试密码登录.
  - `allow`: 允许使用二维码. 先尝试密码登录, 失败后使用二维码登录. (推荐)
  - `forbid`: 禁用二维码登录. 仅允许密码登录. 密码为空时会引发错误.

### 数据库

  键: `feed`

  ~~~ yaml
  keepdays: 3
  archivedays: 180
  ~~~

  > `keepdays`: integer

  说说在本地缓存的天数、爬取说说过程中时间上的截止条件. _可选_. 默认为3.

--- 
  > `archivedays`: integer

  归档存储时间. 超出`keepdays`后, 说说的内容会被舍弃, 用于点赞的必要参数将保留更长时间.

### 机器人

  键: `bot`

  ~~~ yaml
  method: webhook
  token: hereisyourtoken
  accept_id: 123456789
  # auto_start: True
  # daily: ...
  # proxy: ...
  webhook: ...
  ~~~

  > `method`: string (enum)

  转发模式. __重要__. 

  - `refresh`: 定时刷新模式. 功能受限. 无法接受外部指令, 只定时爬取说说并转发. 在移动设备上或有用武之地.
  - `polling`: 轮询模式. 每隔一定时间向telegram api查询是否有待处理的事件. 适合快速上手、调试, 以及主机未绑定域名的情况.
  - `webhook`: 向telegram api注册伺服器. 当有待处理事件时, telegram向该伺服器推送事件. 推荐, 适合服务器已绑定域名和获取证书的情况.

--- 
  > `token`: string

  bot token. __重要__. 指定机器人的唯一参数.

--- 
  > `accept_id`: list[integer] -> integer

  有权沟通bot的用户和对话. __重要__. 通常只需填写用户本身的`userid`即可. 未列入该列表的实体向bot发送的指令会被拒绝.

  __FutureWarning__: `accept_id`变更为`int`类型. 在`2.0.0rc2`之前, 列表形式的`accept_id`会引发警告以提示用户更改配置; 该版本及之后会引发错误.

--- 
  > `auto_start`: boolean

  是否在程序启动后自动执行`/start`指令. _可选_. `2.0.0b2`后默认为False. 

--- 
  > `interval`: integer

  自动刷新间隔.  _可选_. 为0时不自动刷新. 默认为0.

  __FutureWarning__: 自`2.0.0b5`起, `interval`参数将被弃用. 请使用`daily`作为代替. 目前, `interval`将被固定为`86400(time=now, days=everyday)`

  > `daily`: [dailyConfig](#定时), _可选_.

  > proxy: [proxyConfig](#代理), _可选_. 

  > webhook: [webhookConfig](#webhook), _可选_. 

#### 定时

  键: `bot.daily`

  _可选_, 顾名思义, 每日定时运行bot.

  > `time`: string | list

  _可选_, 每天运行bot的时间. 可指定多个时间, 默认为当前时间.

  - 字符串时间, 必须是%H:%M格式, 如"12:00"
  - 空格分隔的字符串, 如"08:00 14:00 17:00"
  - 字符串列表, 如["08:00", "14:00", "17:00"]
  
  > `days`: list (1~7)

  表示要自动运行的日期(星期). 如`[1, 2, 3, 4, 5]`表示仅周一到周五运行.
  _可选_, 默认每天运行.

#### 代理

  键: `bot.proxy`

  该配置项将传入`python-telegram-bot`内的`requests`中. _可选_. 
  本条目的书写请参考`python-telegram-bot`的[Working Behind a Proxy][1]章节.

  ~~~ yaml
  proxy_url: socks5 OR socks5h://URL_OF_THE_PROXY_SERVER:PROXY_PORT,
    # Optional, if you need authentication:
    # urllib3_proxy_kwargs:
    #   username: PROXY_USER
    #   password: PROXY_PASS
  ~~~

  > `proxy_url`: string (url)

  支持`http`, `socks5`, `socks5h`, 支持代理认证.
  注: 要使用`socks5`, 需安装额外版本: `pip install python-telegram-bot[socks]`
  

#### webhook

  键: `bot.webhook`

  _可选_, __仅当使用webhook时设置此项__

  ~~~ yaml
  # 服务器地址, 重要
  server: ${oc.env:SERVER_NAME}
  # prefex: tg
  port: ${oc.env:WEBHOOK_PORT}
  cert: /etc/letsencrypt/live/${bot.webhook.server}/cert.pem
  key: /etc/letsencrypt/live/${bot.webhook.server}/privkey.pem
  # max_connections: 40
  ~~~

  > `server`: string (domain)

  用于注册webhook的服务器地址, __重要__.

--- 
  > `prefex`: string

  注册webhook时的path prefex. _可选_. webhook的地址为 `https://{server}/{prefex}/{token}`, prefex为空时为 `https://{server}/{token}`. `prefex`可能会为反向代理提供方便.

--- 
  > `port`: integer (port)

  `python-telegram-bot`会设立一个小的服务器用于监听telegram推送的事件. `port`指定该服务器监听的端口. 由于`python-telegram-bot`的限制, 仅支持80/88/443/8443端口. _可选_. 默认80.

--- 
  > `cert`: string (path)

  证书路径. _可选_. 若已配置反代则不需要再设置证书和私钥. 注意, telegram要求注册webhook的网址必须开启https.

--- 
  > `key`: string (path)

  私钥路径. _可选_. 若已配置反代则不需要再设置证书和私钥.

--- 
  > `max_connections`: integer

  服务器的最大连接数. _可选_. 默认40.

## 快速开始

~~~ yaml
bot: 
  token: ?
  accept_id: ?
  proxy: ?      # 可选
~~~

填写上述`?`, 以交互模式进入程序. 输入qq即可开始.

[1]: (https://github.com/python-telegram-bot/python-telegram-bot/wiki/Working-Behind-a-Proxy) "Working Behind a Proxy"
