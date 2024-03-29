说明
======================

-------------------------
名词解释
-------------------------

^^^^^^^^^^^^^^^^^^^^^^^^^
与 Telegram 通讯
^^^^^^^^^^^^^^^^^^^^^^^^^

.. glossary::

   polling
      通过轮询的方式从 `!telegram` 获取更新。只要能够请求 `!telegram api` 便可以工作。

   webhook
      在本地设置一个服务器，向 `!telegram api` 注册这个服务器的地址。当有更新时，由 `!telegram api` 向此服务器
      发送更新。因为需要让 `!telegram api` 能够访问到此服务器，因此需要满足更复杂的条件：域名、公网IP、开启SSL等。
      相比 :term:`polling` 更节省资源。

      .. seealso:: :external:meth:`~aiogram.dispatcher.dispatcher.Dispatcher.start_polling`


^^^^^^^^^^^^^^^^^^^^^^^^^
代理
^^^^^^^^^^^^^^^^^^^^^^^^^

.. glossary::

   http_proxy
      支持 ``http`` ``https``. 支持指定用户名和密码，如 `!https://username:password@your.proxy.com:1234`

   socks_proxy
      支持 ``socks`` ``socks5`` ``socks5h``. Supported by `pysocks <https://pypi.org/project/PySocks/>`_.
      支持用户名和密码，如 `!socks5h://username:password@your.proxy.com:7890`.


^^^^^^^^^^^^^^^^^^^^^^^^^
其他
^^^^^^^^^^^^^^^^^^^^^^^^^

.. glossary::

   docker secrets
      这里主要指 docker compose 对 secrets 的支持。见 `compose-file-v3/secrets <https://docs.docker.com/compose/compose-file/compose-file-v3/#secrets>`_ 。
      您在 :file:`docker-compose.yml` 中指定 ``secrets`` 后，对应的 ``secrets`` 会以文件的形式映射到 :file:`/run/secrets`.
      这也是 :option:`qzone3tg -s` 的默认值。


--------------------------
命令行
--------------------------

^^^^^^^^^^^^^^^^^^^^^^^^^
Module: qzone3tg
^^^^^^^^^^^^^^^^^^^^^^^^^

.. program:: qzone3tg

.. option:: --conf <config path>, -c <config path>

    指定配置文件，默认为 :file:`./config/settings.yml`

.. option:: --secrets <secrets dir>, -s <secrets dir>

    指定 :term:`docker secrets` 目录，默认为 :file:`/run/secrets`

.. option:: --version -v

    打印版本后退出


-------------------------
已知问题
-------------------------

1. ``20003：网络环境存在风险``：密码登录一般会触发验证码或是短信动态验证码。我们能够解算验证码的答案（详见 aioqzone ），但（据推测）无法通过后续的环境信息检查。
   解决方法一是在经常使用的网络环境下部署服务，比如家庭网络中的NAS；二是使用二维码登录，通常在一段时间之后密码登录就不会触发验证码了。
2. 超长说说抓取不全。从处理流程上，说说长度可以分为一般、长和超长。后两种情况的区别在于，在网页版 Qzone 上，前者可以通过点击“更多”查看全部内容，而后者会被截断。
   这一问题尚无解决方案，但向TG发送的消息会带有原说说的链接，用户可以在移动设备上点击链接跳转到移动端 Qzone 查看全文。
3. 消息重复：消息重复主要有两个原因。一是 Qzone API 会返回一些内容一致但时间略有差异的说说，在 ``0.6.1`` 之前我们并没有处理这类问题。
   二是 Telegram API 造成的，发送消息时 Telegram 向程序报告发生了超时错误，而我们处理此错误的行为是重发。然而实际上消息是有可能发送到用户端的,
   不过我们无从知晓消息是否送达。因此，为了尽可能保证每一条消息的送达，我们不应该不重发超时消息。这就可能导致您收到重复的消息，**这种情况在网络条件不好的服务器上更为常见**。
