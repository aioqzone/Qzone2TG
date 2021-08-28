# Qzone2TG

爬取QQ空间说说并转发到telegram

> tx修复了[#11](https://github.com/JamzumSum/Qzone2TG/issues/11)的接口问题. 2.0.0b2做出了适应性修改以应对新接口. <br>
> 2.0.0b3修复了大量bug(x 优化了对'转发'的处理

> [Project board](https://github.com/JamzumSum/Qzone2TG/projects/2)</br>
> [v2.0.0b3][4] availible now!</br>

## 功能

* 自动登录空间, ~~cv过验证~~
* 二维码登录
* 爬取说说文本
* 爬取说说图片
* 爬取说说转发
* 点赞(应用消息的点赞有时间限制)
* 过滤部分广告
* 简单的tg机器人, 支持webhook

## 截图

> 咕咕咕

## 需求

* 一台服务器
  * 一切可运行`python`及`nodejs`的环境均可, 甚至包括tmux.
  * 开启webhook需要域名和正确的DNS解析. 难以满足此要求可以使用`polling`或`refresh`模式.
* 可访问tg的网络环境, 以下二选一:
  * 服务器可访问telegram api
  * 有可用的代理
* 一个开通了空间的QQ号
* 一个属于你的tg机器人, 得到token
* 取得你的用户ID(acceptID)

### Telegram commands

```
start - Force refresh and resend all feeds.
refresh - Refresh and send any new feeds.
resend - Resend any unsent feeds.
help - Get help info.
```

## 安装

可选择docker image或直接安装.

### Docker Image

> 感谢 @TigerCubDen 

请移步[wiki][5]

### 源码安装

1. 安装`nodejs` (若不使用账密登录可跳过此项)
2. 请确保安装了`git`, `python3.8+`和对应的`pip`及`setuptools`.
3. 

  ``` shell
  # clone本项目
  git clone https://github.com/JamzumSum/Qzone2TG.git
  cd Qzone2TG

  # 安装依赖
  pip install -e .

  # 建立配置文档. 
  mkdir config
  # 复制示例配置. 也可以参考wiki写配置
  cp misc/example.yaml config/config.yaml

  vim config.yaml     # 使用趁手的编辑器
  # 填写qq, tg bot token, acceptId以及可选的代理
  ```

## 运行

### 配置文件

应用的配置文件在`config`目录下的`config.yaml`. 配置文件示例在`misc`目录下的`example.yaml`.

配置各项的含义请参考[wiki][3]

### 启动

``` shell
python3 -m qzone2tg
# 输入密码或跳过
```

注意, 当允许保存密码时, 您的密码将在配置文件中无损失地存储. __脚本能够无需密钥地还原出您的密码, 您的管理员和攻击者也能够做到这一点.__ 请确保您主机或伺服器的安全性. 
因此 __强烈建议__ 不保存密码, 即在配置文件中保持`savepwd`为`False`(默认).

注意, 如果您的存储不安全, 攻击者可能通过缓存的cookie __直接操作您的QQ空间__. 

## 卸载

|data directory |description  |
|:--------------|:------------|
|data           |保存数据库     |

脚本没有在Qzone2TG文件夹外存储数据. 

如果您需要完全卸载:
1. 删除clone的源文件夹, 在未被修改的情况下, 是`Qzone2TG`
2. _可选的_  删除安装的依赖:

    ``` shell
    #您可以自行选择卸载哪些扩展.
    pip3 uninstall python-telegram-bot lxml omegaconf tencentlogin
    ```

## Credits

> Versions before [v1.3.0](https://github.com/JamzumSum/Qzone2TG/releases/tag/v1.3.0) draw lessons of [qzone](https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py), @bufuchangfeng, no licence.

### Third-Party

- lxml: [BSD-3](https://github.com/lxml/lxml/blob/master/LICENSE.txt)
- omegaconf: [BSD-3](https://github.com/omry/omegaconf/blob/master/LICENSE)
- python-telegram-bot: [LGPL-3](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/LICENSE)
- tencentlogin: [AGPL-3](https://github.com/JamzumSum/QQQR/blob/master/LICENCE)

## License

- [AGPL-3.0](https://github.com/JamzumSum/Qzone2TG/blob/master/LICENSE)
- __不鼓励、不支持一切商业使用__

[1]: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Working-Behind-a-Proxy "Working Behind a Proxy"
[2]: https://code.visualstudio.com/docs/python/environments#_environment-variable-definitions-file "Use of the PYTHONPATH variable"
[3]: https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3 "配置文件"
[4]: https://github.com/JamzumSum/Qzone2TG/releases/tag/2.0.0b3 "v2.0.0 beta3"
[5]: https://github.com/JamzumSum/Qzone2TG/wiki/Docker%E9%83%A8%E7%BD%B2 "Docker部署"
