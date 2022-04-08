构建
========================

.. note:: 注意，此页面提供给开发人员，普通用户一般不必查看此页面。

.. note:: 注意，本页面提供的命令均建立在您已经安装 `poetry <https://python-poetry.org>`_ 的前提下。

========================
构建 python 包
========================

.. code-block:: shell

    poetry build

sdist & bdist 在 :file:`dist/` 下

========================
构建 python 压缩包
========================

打包程序需要的所有依赖，在安装 :program:`python` 和 :program:`node` 的环境上开箱即用。

.. code-block:: shell

    python src/pack.py -z "app.zip"     # 帮助：python src/pack.py -h

.. note::

    1. 打包脚本运行于 py310 下
    2. 系统相关，linux 系统下打包就只能用于 linux
    3. 脚本需要调用 :program:`npm` 和 :program:`pip`

使用：``python app.pyz``

========================
构建 Sphinx 文档
========================

.. code-block:: shell

    poetry install -E doc
    poetry run sphinx-build doc/source doc/build/html -D release=$(poetry version -s)

html 在 :file:`doc/build/html` 下

========================
构建 docker 镜像
========================

.. code-block:: shell

    docker build -f docker/Dockerfile -t qzone3tg:$(poetry version -s) .
