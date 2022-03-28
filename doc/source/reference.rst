References
======================

-------------------------
Terms
-------------------------

.. glossary::

   polling
      通过轮询的方式从 `!telegram` 获取更新。只要能够请求 `!telegram api` 便可以工作。

   webhook
      在本地设置一个服务器，向 `!telegram api` 注册这个服务器的地址。当有更新时，由 `!telegram api` 向此服务器
      发送更新。因为需要让 `!telegram api` 能够访问到此服务器，因此需要满足更复杂的条件：域名、公网IP、开启SSL等。
      相比 :term:`polling` 更节省资源。

      .. seealso:: :external:meth:`telegram.ext.Updater.start_polling`

   http_proxy
      支持 ``http`` ``https``. 支持指定用户名和密码，如 `!https://username:password@your.proxy.com:1234`

   socks_proxy
      支持 ``socks`` ``socks5`` ``socks5h``. Supported by `pysocks <https://pypi.org/project/PySocks/>`_.
      支持用户名和密码，如 `!socks5h://username:password@your.proxy.com:7890`.

   docker secrets
      这里主要指 docker compose 对 secrets 的支持。见 `compose-file-v3/secrets <https://docs.docker.com/compose/compose-file/compose-file-v3/#secrets>`_ 。
      您在 :file:`docker-compose.yml` 中指定 ``secrets`` 后，对应的 ``secrets`` 会以文件的形式映射到 :file:`/run/secrets`.
      这也是 :option:`qzone3tg -s` 的默认值。

--------------------------
Programs
--------------------------

.. rubric:: Module: qzone3tg

.. program:: qzone3tg

.. option:: --conf <config path>, -c <config path>

    指定配置文件，默认为 :file:`./config/settings.yml`

.. option:: --secrets <secrets dir>, -s <secrets dir>

    指定 :term:`docker secrets` 目录，默认为 :file:`/run/secrets`

.. option:: --version -v

    打印版本后退出
