Log 配置
=========================

.. currentmodule:: qzone3tg.settings

.. autopydantic_settings:: LogConf

--------------------------
日志配置文件
--------------------------

.. versionadded:: 0.3.2

支持使用专门的日志配置文件。日志配置文件使用 YAML 语法。参考:
`Configuration dictionary schema <https://docs.python.org/3/library/logging.config.html#logging-config-dictschema>`_

以下配置以 ``DEBUG`` 等级输出到标准输出，以 ``ERROR`` 等级输出到 :file:`log/error.log`，
日志文件按日刷新并标记。

.. literalinclude:: ../../../config/log.yml
    :language: yaml

.. hint::

    当您在 docker 容器中输出日志文件时，不要忘记把日志目录映射到宿主机上。
