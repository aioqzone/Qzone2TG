# Qzone2TG

爬取QQ空间说说并转发到telegram

<div style="text-align:left">

<!-- <img src="https://img.shields.io/github/stars/JamzumSum/Qzone2TG?style=social"> -->

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

> We are using [QzEmoji][qzemoji] to provide a `link2title` service. We'll appreciate your contirbution if you're willing to 'name' a emoji link.

> [v2.2][latest] availible now!<br>
> New photo list API is added. We'll fetch photos with the same quality as those in album mode. <br>
> We introduce a little bit concurrency in 2.2.1a1. Hopes this will accelerate our pipeline. <br>
> For other announcements, see [Discussion][notice] and my [blog][blog]

---

## 功能

* 自动登录空间, ~~cv过验证~~(broken)
* 二维码登录
* 爬取说说文本、图片、视频以及常见转发格式
* 点赞(应用消息的点赞有时间限制)
* 过滤广告
* 简单的tg机器人, 支持webhook

## 截图

> See my [blog][blog] for screenshots, demo vedio, tutorials in detail and other resources. 
> (咕咕咕

## 需求

* 一台服务器
  * 一切可运行`python`及`nodejs`的环境均可*, 甚至包括Termux.
  * 开启webhook需要域名和正确的DNS解析. 难以满足此要求可以使用`polling`或`refresh`模式.
* 可访问tg的网络环境, 以下二选一:
  * 服务器可访问telegram api
  * 有可用的代理
* QQ号和tg用户ID
* tg机器人的`bot token`

> *运行环境: **U**in-**P**wd登录和验证码解析需要`nodejs`. 如果您的二维码策略总保持`force`, 甚至不需要安装`nodejs`. 非windows或linux系统可能会遇到keyring的配置问题, 但这可以通过交互模式或命令行传参的方式解决. 或者保持二维码策略为`force`可以避免UP登录带来的一切问题(

## 安装

|安装方式                              |建议    |
|:-----------------------------------|:------:|
|[docker镜像][docker](感谢@TigerCubDen)|✔️     |
|源码安装(develop install)             |✔️     |
|常规pip安装                           |❌     |

### 安装依赖

1. 安装`nodejs` (若不使用账密登录可跳过此项)
2. 请确保安装了`git`, `python3.8+`和对应的`pip`及`setuptools`.
3. linux环境请确保安装`gnome-keyring`:
  ~~~ shell
  apt install gnome-keyring
  ~~~

### 安装Qzone2TG

<details>
<summary> 源码安装(develop install) </summary>

``` shell
# clone本项目
git clone https://github.com/JamzumSum/Qzone2TG.git
cd Qzone2TG

# 安装依赖
pip install -e .
# 复制示例配置. 也可以参考wiki写配置
cp misc/example.yaml config/config.yaml
```

</details>


<details>
<summary> pip安装 </summary>

~~~ shell
# 安装到site-package
pip install git+https://github.com/JamzumSum/Qzone2TG.git
# 构建工作区
mkdir Qzone2TG && cd Qzone2TG && mkdir config
~~~

</details>

## 运行

### 配置文件

请参考[wiki][conf]

~~~ shell
vim config/config.yaml
# 填写qq, bot token, acceptId以及可选的代理
~~~

### 启动

- pip develop install: `python src/qzone2tg`
- pip安装: `python -m Qzone2TG`

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
1. - develop install: 删除`Qzone2TG`文件夹
   - pip安装: `pip uninstall qzone2tg`
2. _可选的_  删除安装的依赖:

    ``` shell
    # python依赖
    pip uninstall python-telegram-bot lxml cssselect omegaconf keyring tencentlogin qzemoji
    ```

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



[conf]: https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3 "配置文件"
[latest]: https://github.com/JamzumSum/Qzone2TG/releases/tag/2.2.1a4 "2.2.0"
[docker]: https://github.com/JamzumSum/Qzone2TG/wiki/Docker%E9%83%A8%E7%BD%B2 "Docker部署"
[notice]: https://github.com/JamzumSum/Qzone2TG/discussions/categories/announcements "Announcement📣"
[qzemoji]: https://github.com/JamzumSum/QzEmoji "Translate Qzone Emoji to Text"
[blog]: https://github.com/JamzumSum/Qzone2TG "咕咕咕"
