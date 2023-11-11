使用
==============================

------------------------------
命令
------------------------------

.. option:: /start

    启动 Bot。这会触发一次刷新，不存在于数据库（:obj:`bot.storage <.BotConf.storage>`）中的说说会被发送
    到 `!telegram api`.

.. option:: /status

    查询 Bot 状态。目前记录的状态包括：

    * 程序启动时间
    * 上次登录时间
    * 心跳状态
    * 上次心跳时间
    * 上次清理数据库时间
    * 网速估计

.. option:: /status debug

    查询 Bot 状态，附加调试信息。

    .. hint::

        :command:`/status debug` 命令可以用来重启 :command:`/status debug` 定时任务
        （:obj:`log.debug_status_interval <.LogConf.debug_status_interval>`）。

.. option:: /up_login

    主动密码登录。登录成功后可重启心跳。

.. option:: /qr_login

    主动二维码登录。登录成功后可重启心跳。

.. option:: /em <eid>

    查询一个表情。这会从 Qzone 服务器上拉取一张图片，并将此发送至 `!telegram api`.

.. option:: /em <eid> <text>

    设置自定义表情文本。比如，您收到的文本中包含表情代码 ``[em]e8001111[/em]``。您通过
    :command:`/em 8001111` 查看此表情，并为此表情定义一个文本：:command:`/em 8001111 这是文本`.
    此后您收到的文本中，``[em]e8001111[/em]`` 会被自动替换为 `![/这是文本]`。

.. option:: /like

    .. versionadded:: 0.3

    由于 `!telegram api` 的限制，相册类型的消息不能包含“按钮”。因此点赞相册类消息时，需要用户回复该消息并发送命令
    :command:`/like`。

.. option:: /block

    .. versionadded:: 0.7.5

    动态屏蔽某人的说说。使用此命令需要回复一条消息，若此通过此消息未能查询到uin，则会回复一条提示。若未回复某条消息，则会发送
    /block 系列命令的帮助信息。

.. option:: /block add <uin>

    动态屏蔽某个uin。如果通过 /block 消息的方式未能成功，可以手动屏蔽uin。

.. option:: /block rm <uin>

    取消屏蔽某个uin。

.. option:: /block list

    列出所有被屏蔽的uin。

.. option:: /comment list

    .. versionadded:: 0.9.4

    列出所引用说说的评论。

.. option:: /comment add <content>

    .. versionadded:: 0.9.4

    评论所引用的说说。

.. option:: /comment add private <content>

    .. versionadded:: 0.9.4

    私密评论所引用的说说。

.. option:: help

    发送帮助信息。

------------------------------
登录
------------------------------

Qzone3TG 有两种登录方式，二维码登录和密码登录。

- 二维码登录需要用户使用QQ或TIM移动端扫码授权，用户一段时间不响应将尝试其他登录方法。
- 密码登录对登录IP的要求更高，通常新环境下密码登录不会成功。个别情况下密码登录会向您的绑定手机发送动态验证码，此时您应当回复短信中的6位验证码。用户一段时间不反应将尝试其他登录方法。
- 所有方法均无法登录时，登陆失败。
