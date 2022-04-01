快速上手
==============

==============
部署
==============

Qzone3TG 支持且仅支持 docker 部署。当然，若您是 Python 开发者，您可以直接克隆本仓库并安装软件包。

0. 确保您的服务器上安装了 :program:`docker`，确保能够使用 :program:`docker-compose`。
1. Qzone3TG 支持文件配置和环境变量配置：:download:`文件配置模板 <../../config/test.yml>`；:download:`docker-compose 模板 <../../docker/docker-compose.yml>`。
2. 按照下文提供的范例编辑您的配置文件，配置的具体含义见 :doc:`文档 <config/index>`。
3. 运行：:command:`docker-compose up -f docker/my-compose.yml -d`。

==============
配置
==============

-------------------------
使用文件配置
-------------------------

由于 yaml 具有良好的可读性，我们目前支持且仅支持 yaml 配置。

最小配置文件：

.. literalinclude:: ../../config/test.yml
    :language: yaml
    :lines: 1-3

最大（最全）配置文件：

.. literalinclude:: ../../config/test.yml
    :language: yaml
    :lines: 5-

.. warning::
    您下载的 yaml 模板既包含最大配置，又包含最小配置，之间用 ``---`` 分割。这是出于展示和简化文件的目的。
    您编辑完成的配置文件不应当包含分割线 ``---``。

-------------------------
使用环境变量配置
-------------------------

Qzone3TG 支持从环境变量中读取配置。:program:`docker-compose` 的配置文件可以很方便地配置容器环境变量。
如果您的配置项较少，推荐使用这种写法。有关 :program:`docker-compose` 文件的语法，请参考
`docker compose 文档 <https://docs.docker.com/compose/compose-file/compose-file-v3>`_ 。

.. literalinclude:: ../../docker/docker-compose.yml
    :language: yaml
    :emphasize-lines: 9-16
