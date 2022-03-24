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
构建 Sphinx 文档
========================

.. code-block:: shell

    poetry install -E doc
    poetry run sphinx-build doc/source doc/build

html 在 :file:`doc/build/html` 下

========================
构建 docker 镜像
========================

.. code-block:: shell

    docker build -f docker/Dockerfile --network host -t qzone3tg:$(poetry version -s) -t qzone3tg:latest .
