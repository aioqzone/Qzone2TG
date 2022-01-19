# Qzone2TG

爬取QQ空间说说并转发到telegram

<div name="badge" style="text-align:left">

<a href="https://github.com/JamzumSum/Qzone2TG/discussions/37">
<img src="https://img.shields.io/badge/python-3.9-blue?logo=python">
</a>

<a href="https://github.com/JamzumSum/QQQR/actions/workflows/interface.yml">
<img src="https://github.com/JamzumSum/QQQR/actions/workflows/interface.yml/badge.svg">
</a>

<a href="https://github.com/JamzumSum/Qzone2TG/actions/workflows/python-app.yml">
<img src="https://github.com/JamzumSum/Qzone2TG/actions/workflows/python-app.yml/badge.svg">
</a>

<a href="https://t.me/qzone2tg">
<img src="https://img.shields.io/badge/dynamic/xml?label=telegram&query=%2F%2Fdiv%5B%40class%3D%22tgme_page_extra%22%5D&url=https%3A%2F%2Ft.me%2Fqzone2tg&style=social&logo=telegram">
</a>

<div name="version">
<a href="https://github.com/JamzumSum/Qzone2TG/tree/2.2d">
<img src="https://img.shields.io/badge/dynamic/xml?color=yellow&label=dev&query=%2F&url=https%3A%2F%2Fraw.githubusercontent.com%2FJamzumSum%2FQzone2TG%2F2.2d%2Fsrc%2Fqzone2tg%2FVERSION&logo=github&prefix=v">
</a>

<a href="https://github.com/JamzumSum/Qzone2TG/releases">
<img src="https://img.shields.io/github/v/tag/JamzumSum/Qzone2TG?label=beta&include_prereleases&logo=github&color=green">
</a>

<a href="https://github.com/JamzumSum/Qzone2TG/releases/latest">
<img src="https://img.shields.io/github/v/release/JamzumSum/Qzone2TG?display_name=tag&label=stable&logo=github&color=success">
</a>

<a href="https://hub.docker.com/repository/docker/jamzumsum/qzone2tg">
<img src="https://img.shields.io/docker/v/jamzumsum/qzone2tg/latest?logo=docker&label=docker">
</a>
</div>

</div>

> We are using [QzEmoji][qzemoji] to provide a `link2title` service. We'll appreciate your contirbution if you're willing to 'name' a emoji link.

> [2.2.2][latest] 已更新! <br>
> 点击上方徽章, 加入我们的TG频道和讨论组, 在 [Github Discussion][notice] 查看更多信息.<br>
> 关于3.0: 3.0版本是一个重写版本. 考虑到目前的进度和作者的时间安排, 3.0的到来：_遥遥无期_

---

## 功能

- [x] 自动登录空间
- [ ] ~~cv过验证(broken now)~~
- [x] 二维码登录
- [x] 爬取说说文本、图片、视频以及常见转发格式
- [x] 点赞(应用消息的点赞有时间限制)
- [x] 过滤广告
- [x] 简单的tg机器人, 支持webhook

## 需求

* 一台服务器
  * 一切可运行`python`及`nodejs`的环境均可*, 甚至包括Termux.
  * 开启webhook需要域名和正确的DNS解析. 难以满足此要求可以使用`polling`或`refresh`模式.
* 可访问tg的网络环境, 以下二选一:
  * 服务器可访问telegram api
  * 有可用的代理
* QQ号和tg用户ID
* tg机器人的`bot token`

> *运行环境: **U**in-**P**wd登录和验证码解析需要`nodejs`. 如果您只使用二维码登录, 甚至不需要安装`nodejs`. 非windows或linux系统可能会遇到keyring的配置问题, 但这可以通过交互模式或命令行传参的方式解决. 或者保持二维码策略为`force`可以避免UP登录带来的一切问题(

## 安装

|安装方式                                 |版本    |建议  |
|:---------------------------------------|:-----:|:---:|
|[docker镜像][docker](感谢@TigerCubDen)   |w/o dev|✔️   |
|[pip安装](../../wiki/pip部署#安装Qzone2TG)|all    |❌   |

> 点击链接转到对应的wiki :D

## 运行

### 配置文件

请参考[wiki][conf]

``` shell
vim config/config.yaml
# 填写qq, bot token, acceptId以及可选的代理
```

### 启动

- pip develop install: `python src/qzone2tg`
- pip安装: `python -m qzone2tg`

---

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
- develop install: 删除`Qzone2TG`文件夹
- pip安装: `pip uninstall qzone2tg`


## Credits

> Versions before [v1.3.0](https://github.com/JamzumSum/Qzone2TG/releases/tag/v1.3.0) draw lessons of [qzone](https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py), @bufuchangfeng, no licence.

## License

- [AGPL-3.0](LICENSE)
- __不鼓励、不支持一切商业使用__

### Third-Party

- lxml: [BSD-3](https://github.com/lxml/lxml/blob/master/LICENSE.txt)
- cssselect [BSD](https://github.com/scrapy/cssselect/blob/master/LICENSE)
- omegaconf: [BSD-3](https://github.com/omry/omegaconf/blob/master/LICENSE)
- python-telegram-bot: [LGPL-3](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/LICENSE)
- keyring: [MIT](https://github.com/jaraco/keyring/blob/main/LICENSE)
- tencentlogin: [AGPL-3](https://github.com/JamzumSum/QQQR/blob/master/LICENCE)
- qzemoji: [MIT](https://github.com/JamzumSum/QzEmoji/blob/main/LICENSE)



[conf]: ../../wiki/配置文档 "配置文件"
[latest]: ../../releases/tag/2.2.2.post1 "2.2.2.post1"
[docker]: ../../wiki/Docker部署 "Docker部署"
[notice]: ../../discussions/categories/announcements "Announcement📣"
[qzemoji]: ../../../QzEmoji "Translate Qzone Emoji to Text"
[blog]: https://github.com/JamzumSum/Qzone2TG "咕咕咕"
