安全实践
========

本页汇总部署 Qzone3TG 时的安全建议。默认配置的目标是“能够运行”，
并不保证适合直接暴露在公网。请根据实际环境采用以下建议。

.. seealso::

   :doc:`config/index` 介绍了所有配置项；:doc:`build` 介绍了自行构建镜像的方法。

.. currentmodule:: qzone3tg.settings

-------------------------
保护凭据
-------------------------

Qzone3TG 涉及三类敏感信息：

* QQ 密码和 Telegram bot token；
* webhook 的 ``secret_token``；
* 登录成功后保存在数据库中的 QQ 会话 cookie。

^^^^^^^^^^^^^^^^^^^^^^^^^
密码与 bot token
^^^^^^^^^^^^^^^^^^^^^^^^^

密码和 bot token **不会从 YAML 配置文件中读取**。程序只从环境变量或
:term:`docker secrets` 读取它们， **推荐使用后者**，因为环境变量可以通过
:command:`docker inspect` 查看。

.. code-block:: yaml
   :caption: docker-compose.yml

   services:
     qzone:
       secrets:
         - password
         - token
       # 其余配置...

   secrets:
     password:
       file: ./secrets/password
     token:
       file: ./secrets/token

secret 文件名默认为 ``password`` 和 ``token``，程序从 :file:`/run/secrets`
读取；如果使用其他目录，可以通过 :option:`qzone3tg -s` 指定。

.. warning::

   * 不要把 QQ 密码和 bot token 写进 YAML、:file:`docker-compose.yml` 或
     提交到版本库。
     :file:`docker/.env` 等环境变量文件也应当只保存在部署机器上。
   * 密钥文件的权限建议设为 ``600``。
   * bot token 泄露后，请立即在 ``@BotFather`` 中 revoke 并重新生成。

.. note::

   由于容器默认以 uid 1000 运行，bind mount 到 :file:`/app/config` 的配置文件必须
   对该用户可读。若要把配置文件设为 ``600``，请将其所有者改为容器运行用户
   （默认 1000，``chown 1000:1000``）。:term:`docker secrets` 由 Docker 以
   ``0444`` 挂载到容器，源文件设为 ``600`` 不影响容器读取。

^^^^^^^^^^^^^^^^^^^^^^^^^
保护会话 cookie
^^^^^^^^^^^^^^^^^^^^^^^^^

登录成功后，程序会把 ``p_skey``, ``pt4_token`` 等 cookie 写入
:obj:`bot.storage.database <.StorageConfig.database>` 指向的 SQLite 数据库。
这些 cookie 可以（在有效时间内）直接操作对应的 QQ 账号，应当按密码的级别保护：

* 数据库卷不要共享给其他容器或用户；
* 备份应当加密保存，不再使用时及时删除；
* 怀疑泄露时，修改 QQ 密码、在手机端退出其他设备，并删除数据库卷让程序重新登录。

-------------------------
Webhook 安全
-------------------------

:term:`polling` 模式不需要开放任何入站端口，只有在使用 webhook 时才适用本节配置。

^^^^^^^^^^^^^^^^^^^^^^^^^
设置 secret_token
^^^^^^^^^^^^^^^^^^^^^^^^^

推荐在 :obj:`bot.init_args <.BotConf.init_args>` 中设置
:obj:`secret_token <.WebhookConf.secret_token>`：

.. code-block:: yaml

   bot:
     init_args:
       destination: https://bot.example.com/<随机路径>
       port: 8443
       secret_token: "<随机字符串>"

可以用下面的命令生成一个随机值：

.. code-block:: shell

   openssl rand -hex 32

``secret_token`` 需要是 1–256 个字符，只能包含 ``A-Z``, ``a-z``, ``0-9``,
``_`` 和 ``-``，并且应当独立随机生成，不要复用 bot token 或其他密码。
也可以通过环境变量 ``bot.init_args.secret_token`` 设置。

设置后，Telegram 会在每个 webhook 请求中携带
``X-Telegram-Bot-Api-Secret-Token`` 请求头，程序会校验它并拒绝不匹配的请求。
**不设置 secret_token 时，任何知道 webhook 地址的人都可以伪造 Telegram 更新。**

同时建议把 webhook 路径也设置成随机值: ``destination`` 的 path 部分就是实际的
监听路径，这可以在 ``secret_token`` 之外再加一层防护。

.. note::

   ``secret_token`` 只能写在配置文件或环境变量中，不受 docker secrets 保护；
   请限制配置文件的权限（并确保容器用户可以读取），并避免提交到版本库。

^^^^^^^^^^^^^^^^^^^^^^^^^
用反向代理终止 TLS
^^^^^^^^^^^^^^^^^^^^^^^^^

.. warning::

   当前实现只要求 ``destination`` 使用 HTTPS，并不会在本地用
   :obj:`cert <.WebhookConf.cert>` / :obj:`key <.WebhookConf.key>` 启动 TLS 服务
   （``key`` 目前未参与启动流程）。请勿把容器的 HTTP 端口直接发布到公网。

推荐让反向代理监听 443 并终止 TLS，程序端口只绑定到宿主机回环地址：

.. code-block:: yaml
   :caption: docker-compose.yml

   services:
     qzone:
       ports:
         - "127.0.0.1:8443:8443"

.. code-block:: nginx
   :caption: nginx.conf

   server {
       listen 443 ssl;
       server_name bot.example.com;

       ssl_certificate     /etc/letsencrypt/live/bot.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/bot.example.com/privkey.pem;

       location /<随机路径> {
           proxy_pass http://127.0.0.1:8443;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           # 不要清除 X-Telegram-Bot-Api-Secret-Token
       }
   }

.. note::

   ``location`` 的 path 必须与 ``destination`` 的 path 一致（示例没有改写
   path）。上例的 ``destination`` 没有结尾斜杠；如果写成
   ``location /<随机路径>/``，Nginx 会对 ``/<随机路径>`` 返回 301，而
   Telegram 会把非 2xx 响应视为失败并重试。

.. note::

   镜像默认以非 root 用户运行，webhook 端口应使用 1024 以上的端口（如
   ``8443``），否则默认会因无权限绑定而启动失败（除非额外授予
   ``NET_BIND_SERVICE`` 能力或调整容器的非特权端口范围）。需要监听 443 时，
   请交给反向代理。

如果反向代理也运行在 docker 中，建议把它和本服务放进同一个 docker 网络，
让代理直接访问 ``qzone:8443``，并且完全不发布该端口。

-------------------------
以非 root 用户运行
-------------------------

官方镜像默认使用镜像内的 ``qzone`` 用户（默认 uid/gid 1000，可通过构建参数
``APP_UID`` / ``APP_GID`` 修改）运行。不要为了方便用 compose 的 ``user: root``
或 :command:`docker run --user root` 覆盖它。

.. note::

   如果以 root 启动，entrypoint 会打印警告，修正 :file:`/app/log`、
   :file:`/app/data` 的属主后降权到 ``qzone``。这是为了兼容旧部署或
   root 拥有的挂载卷，修复完成后应去掉这个覆盖。即使修复失败，程序也
   不会回退到 root；此时需要手动修正挂载权限。

.. warning::

   从旧的 root 镜像升级时，已有的 ``qzone-data`` 卷仍然归 root 所有。
   Docker 只在空卷首次创建、从镜像复制数据时才会修正属主，已有数据的卷
   不会被修改，因此升级后可能需要先处理一次：

   临时在 compose 中设置 ``user: "0:0"`` 启动一次，让 entrypoint 修复后
   以 ``qzone`` 运行，然后删掉该设置；也可以直接修正卷的属主：

   .. code-block:: shell

      docker run --rm --user root --entrypoint chown \
        -v <project>_qzone-data:/app/data <image> -R 1000:1000 /app/data

   如果仍在使用宿主机目录（例如旧的 :file:`/var/log/Qzone2TG`），也需要
   对该目录执行 ``chown 1000:1000``。另外，``/app`` 保持 root 所有，
   自定义的数据库或日志路径如果不在 ``/app/log``、``/app/data`` 下，
   也需要放在可写卷中或单独 chown。

可选的加固项：

.. code-block:: yaml
   :caption: docker-compose.yml

   services:
     qzone:
       security_opt:
         - no-new-privileges:true
       cap_drop:
         - ALL

.. warning::

   ``cap_drop: ALL`` 与“以 root 启动并自动修权限”不兼容：后者需要
   ``CHOWN``, ``SETUID`` 和 ``SETGID`` 能力。请先用 root 完成一次性修复，
   再启用 ``cap_drop``。

另外：

* 使用命名卷（如 :file:`qzone-log`、:file:`qzone-data`）或已正确 chown 的
  宿主目录。新建的命名卷会继承镜像中目录的属主，可以直接使用。
* 不要把 :file:`/var/run/docker.sock` 挂载到容器中，这等价于把宿主机的
  root 权限交给容器。
* 生产环境不要使用 ``network_mode: host``，也不要使用 ``privileged``。

-------------------------
减少网络暴露
-------------------------

* 使用 webhook 时，只让反向代理监听公网 443，程序端口只绑定 ``127.0.0.1``
  或只对反向代理所在的 docker 网络可见。
* 不要直接暴露程序端口、Docker API、数据库或日志目录。
* 可选：在反向代理上只允许 Telegram 的 IP 段访问 webhook。地址段见
  `Telegram CIDR <https://core.telegram.org/resources/cidr.txt>`_。
  如果前面还有 CDN/Cloudflare，请先正确配置真实客户端 IP，否则该限制无效。

.. note::

   示例 compose 中的 ``expose: [80]`` 只声明容器端口，不会发布到宿主机，
   不使用 webhook 时可以删除。

-------------------------
其他建议
-------------------------

* **保护管理员账号**：机器人只响应 :obj:`bot.admin <.BotConf.admin>` 指定的
  Telegram 用户。请为该账号开启两步验证，不要与他人共享。
* **降低日志级别**：生产环境使用 ``INFO`` 或更高。``DEBUG`` 会输出登录 cookie
  等敏感信息，日志文件也应当按凭据保护。
* **限制文件权限**：较新的 docker compose 支持 ``umask``，可以设置
  ``umask: "077"``，让数据库和日志文件仅属主可读写：

  .. code-block:: yaml

     services:
       qzone:
         umask: "077"

* **配置只读挂载**：:file:`/app/config` 应以只读方式挂载（示例 compose 已使用
  ``:ro``），避免容器内的进程修改配置。

* **及时更新**：使用官方 ``ghcr.io/aioqzone/qzone3tg`` 镜像，并固定到具体版本
  或 digest， **定期更新以获得依赖的安全修复**。
* **最小化备份范围**：通常只需要备份 :file:`qzone-data` 卷（数据库）；
  备份中包含登录 cookie，请加密保存。
