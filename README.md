# Qzone2TG

爬取QQ空间说说并转发到telegram

## 功能

* 自动登录空间, cv过验证
* 爬取说说文本
* ~~自动获取全文~~(维修中)
* 爬取说说图片
* 爬取说说转发
* QQ原生表情转文字
* 点赞(目前只支持`appid=311`, `typeid=0 or 5`的说说, 即原创和转发)
* 过滤部分广告(待测)
* 简单的tg机器人

(目前)不支持:

* 原生表情
* 爬取视频
* 给应用分享消息点赞
* 显示点赞人数和昵称(已抓取, 为简洁考虑不予实现)
* 显示评论(已抓取, 为简洁考虑不予实现)
* 评论
* 实时刷新
* ....

## 截图

> 等我有空的

## 需求

* 一台服务器
* 访问tg的网络环境, 以下二选一:
  * 你的服务器在国外
  * 你有可用的代理
* 一个开通了空间的QQ号(废话连篇)
* 一个属于你的tg机器人, 得到token
* 取得你的用户ID

## 安装

请确保安装了`git`, `python3`和对应的`pip`.

### 使用shell脚本

``` shell
wget https://raw.githubusercontent.com/JamzumSum/Qzone2TG/master/install.sh
chmod +x install.sh
bash install.sh
```

### 手动安装

``` shell
# 安装依赖
pip3 install python-telegram-bot python-telegram-bot[socks] selenium demjson lxml opencv-python
# clone本项目
git clone https://github.com/JamzumSum/Qzone2TG.git
cd Qzone2TG
# 建立配置文档
cp example.conf config.conf
vim config.conf     # 这里需要一个趁手的编辑器
# 填写qq, tg bot token, userId, 以及可选的代理
```

## 运行

### 配置文件

配置文件在安装目录下的`config.json`

``` json
{
    "qzone": {
        "qq": "这里填QQ",
        "UA": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36 Edg/79.0.309.71",
        "fetch_times": 12,
        "cookie_expire": 9600,
        "log_level": 1
    },
    "feed": {
        "keepdays": 3
    },
    "bot": {
        "token": "这里填bot token",
        "accepted_id": ["这里填用户ID(或是其他chat id)"],
        "proxy": {
            "proxy_url": "socks5://127.0.0.1:1080"
        },
        "method": "polling"
    }
}
```

#### 简单开始

您只需:

1. 配置`qzone`条目下的`qq`项
2. 配置`bot`条目下的`token`项
3. 配置`bot`条目下的`accepted_id`项
4. 如果你使用代理, 还要配置`bot`条目下的`proxy`. 支持`http`, `socks5`, `socks5h`. 如果你的代理需要认证的话, 请一并参见下方链接:

[Working Behind a Proxy][1]

#### 详细配置

请参考[wiki](https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3)

### 启动

``` shell
python3 tg.py
#接下来输入你的密码
```

注意, 您的密码将在配置文件中以 __弱加密__ 存储. 此时其安全性等同于您的操作系统安全性. 换言之, 有权限浏览您配置文件的用户 __完全可能获知您的密码__.

## 卸载

如果您需要完全删除Qzone2TG, 删除整个文件夹即可.

1. 删除clone的源文件夹, 通常叫`Qzone2TG`
2. _可选的_  删除安装的依赖

    ``` shell
    #您可以自行选择卸载哪些扩展.
    pip uninstall python-telegram-bot python-telegram-bot[socks] selenium demjson lxml PIL
    ```

## Credits

@bufuchangfeng [qzone](https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py)

## License

[MIT License](https://github.com/JamzumSum/Qzone2TG/blob/master/LICENSE)

[1]: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Working-Behind-a-Proxy "Working Behind a Proxy"
