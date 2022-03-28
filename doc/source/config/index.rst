配置文件
==============

.. toctree::
   :maxdepth: 1
   :caption: 配置项

   bot <bot>
   log <log>
   qzone <qzone>

.. currentmodule:: qzone3tg.settings

-------------------------
配置总览
-------------------------

配置由两部分构成，一部分是普通配置，支持文件配置或环境变量：

.. tabs::

   .. tab:: 配置文件

      .. literalinclude:: ../../../config/test.yml
         :caption: yaml 配置文件
         :language: yaml
         :lines: 1-3

   .. tab:: 环境变量

      .. code-block:: shell
         :caption: 环境变量

         ${qzone.qq} = 123
         ${bot.admin} = 456

另一部分是密码/密钥，支持 :term:`docker secrets` 或环境变量：

.. tabs::

   .. tab:: 环境变量

      .. code-block:: shell
         :caption: 环境变量

         $password = "my-password"
         $token = "123456:thisistoken"

   .. tab:: docker secrets files

      .. code-block::
         :caption: file: ``${secrets_dir}/password``

         my-password

      .. code-block::
         :caption: file: ``${secrets_dir}/token``

         123456:thisistoken

      ``secrets_dir`` 由 :option:`命令行参数 <qzone3tg -s>` 传入，默认值为 :file:`/run/secrets`.
