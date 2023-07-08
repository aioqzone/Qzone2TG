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

打包程序需要的所有依赖，在安装 :program:`python` 的环境上开箱即用。
完全由 python 代码构成的包会被压缩。参见 :external+python:mod:`zipapp`.

.. code-block:: shell

    bash src/zipapp.sh ./workdir

.. note::

    1. 打包脚本仅适用于 Linux
    2. 脚本需要调用 :program:`pip`

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
