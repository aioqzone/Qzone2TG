快速上手
==============

==============
部署
==============

Qzone3TG 支持且仅支持 docker 部署。当然，若您是 Python 开发者，您可以直接克隆本仓库并安装软件包。

0. 确保您的服务器上安装了 :program:`docker`，确保能够使用 :program:`docker-compose`。
1. 下载 :download:`docker-compose <../../docker/docker-compose.yml>` 配置。
2. 按照 :doc:`文档 <config/index>` 提供的说明编辑 :file:`docker-compose.yml`.
3. 运行：:command:`docker-compose up -d`

==============
配置
==============

使用文件配置：

最小配置文件：

.. literalinclude:: ../../config/test.yml
    :language: yaml
    :lines: 1-3

最大（最全）配置文件：

.. literalinclude:: ../../config/test.yml
    :language: yaml
    :lines: 5-

使用 :file:`docker-compose.yml` 配置：

.. literalinclude:: ../../docker/docker-compose.yml
    :language: yaml
    :emphasize-lines: 9-16
