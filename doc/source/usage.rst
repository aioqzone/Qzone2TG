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

    查询 Bot 状态，附加调试信息。额外包含的信息有：

    * updater.running: :external:obj:`telegram.ext.Updater.running`
    * /status timer: :command:`/status debug` 定时任务状态。

    .. hint::

        :command:`/status debug` 命令可以用来重启 :command:`/status debug` 定时任务
        （:obj:`log.debug_status_interval <.LogConf.debug_status_interval>`）。

.. option:: /relogin

    强制重新登录。

    .. hint:: :command:`/relogin` 命令可以用来重启心跳。

.. option:: /em <eid>

    查询一个表情。这会从 Qzone 服务器上拉取一张图片，并将此发送至 `!telegram api`.

.. option:: /em <eid> <text>

    设置自定义表情文本。比如，您收到的文本中包含表情代码 ``[em]e8001111[/em]``。您通过
    :command:`/em 8001111` 查看此表情，并为此表情定义一个文本：:command:`/em 8001111 这是文本`.
    此后您收到的文本中，``[em]e8001111[/em]`` 会被自动替换为 `![/这是文本]`。

.. option:: help

    发送帮助信息。
