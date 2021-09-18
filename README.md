# Qzone2TG

爬取QQ空间说说并转发到telegram

<div style="text-align:left">

<!-- ![](https://img.shields.io/github/stars/JamzumSum/Qzone2TG?style=social) -->

<img src="https://img.shields.io/badge/python-3.8%2F3.9-blue">

<a href="https://github.com/JamzumSum/QQQR/actions/workflows/interface.yml">
<img src="https://github.com/JamzumSum/QQQR/actions/workflows/interface.yml/badge.svg">
</a>

<a href="https://github.com/JamzumSum/Qzone2TG/releases">
<img src="https://img.shields.io/github/v/tag/JamzumSum/Qzone2TG?include_prereleases&logo=github">
</a> 

<a href="https://github.com/JamzumSum/Qzone2TG/actions/workflows/python-app.yml">
<img src="https://github.com/JamzumSum/Qzone2TG/actions/workflows/python-app.yml/badge.svg">
</a>

<a href="https://hub.docker.com/repository/docker/jamzumsum/qzone2tg">
<img src="https://img.shields.io/docker/v/jamzumsum/qzone2tg/latest?logo=docker">
</a>

</div>

> We are using [QzEmoji](https://github.com/JamzumSum/QzEmoji) to transfer emoji HTML link to text and actual emoji. We'll appreciate your contirbution if you're willing to 'name' a emoji link.

> [2.0.0rc is comming!](https://github.com/JamzumSum/Qzone2TG/discussions/21)<br>
> [Project board](https://github.com/JamzumSum/Qzone2TG/projects/2)<br>
> [v2.0.0rc3][4] availible now! This version supports forwarding video!<br>

## 功能

* 自动登录空间, ~~cv过验证~~(broken)
* 二维码登录
* 爬取说说文本、图片、视频以及常见转发格式
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

<details>

> 自`2.0.0b4`起, 脚本会自动设置如下命令. (感谢 @TigerCubDen)

```
start - Force refresh and resend all feeds.
refresh - Refresh and send any new feeds.
resend - Resend any unsent feeds.
help - Get help info.
```

</details>

## 安装

可选择docker image或直接安装.

### Docker Image

> 感谢 @TigerCubDen 

请移步[wiki][5]

### 源码安装

> 目前仍支持python3.8, 但推荐使用python3.9. 不排除未来停止py38支持的可能. 

1. 安装`nodejs` (若不使用账密登录可跳过此项)
2. 请确保安装了`git`, `python3.8+`和对应的`pip`及`setuptools`.
3. 依序执行:

  ``` shell
  # clone本项目
  git clone https://github.com/JamzumSum/Qzone2TG.git
  cd Qzone2TG

  # 安装依赖
  pip install -e .

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
python src/__main__.py
```

## 卸载

|data directory |description  |
|:--------------|:------------|
|data           |保存数据库     |

您的密码保存于系统的keyring中. 除此之外, 脚本没有在Qzone2TG文件夹外存储数据. 

删除密码:
~~~ shell
keyring del qzone2tg <your-qq>
~~~

如果您需要完全卸载:
1. 删除clone的源文件夹, 在未被修改的情况下, 是`Qzone2TG`
2. _可选的_  删除安装的依赖:

    ``` shell
    # python依赖
    pip3 uninstall python-telegram-bot lxml omegaconf keyring tencentlogin qzemoji
    ```

## Credits

> Versions before [v1.3.0](https://github.com/JamzumSum/Qzone2TG/releases/tag/v1.3.0) draw lessons of [qzone](https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py), @bufuchangfeng, no licence.

### Third-Party

- lxml: [BSD-3](https://github.com/lxml/lxml/blob/master/LICENSE.txt)
- omegaconf: [BSD-3](https://github.com/omry/omegaconf/blob/master/LICENSE)
- python-telegram-bot: [LGPL-3](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/LICENSE)
- keyring: [MIT](https://github.com/jaraco/keyring/blob/main/LICENSE)
- tencentlogin: [AGPL-3](https://github.com/JamzumSum/QQQR/blob/master/LICENCE)
- qzemoji: [MIT](https://github.com/JamzumSum/QzEmoji/blob/main/LICENSE)

## License

- [AGPL-3.0](https://github.com/JamzumSum/Qzone2TG/blob/master/LICENSE)
- __不鼓励、不支持一切商业使用__

[1]: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Working-Behind-a-Proxy "Working Behind a Proxy"
[2]: https://code.visualstudio.com/docs/python/environments#_environment-variable-definitions-file "Use of the PYTHONPATH variable"
[3]: https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3 "配置文件"
[4]: https://github.com/JamzumSum/Qzone2TG/releases/tag/2.0.0rc3 "2.0.0 release candidate 3"
[5]: https://github.com/JamzumSum/Qzone2TG/wiki/Docker%E9%83%A8%E7%BD%B2 "Docker部署"
