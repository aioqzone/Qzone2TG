# Qzone2TG

爬取QQ空间说说并转发到telegram

> - 2021-1-2 Update: 单元测试还不是很好用
> - 有的时候验证还是过不去 抓下来的拼图有时候是反的 算法说实话也太直觉了
> - 现在各个模块还是有大量的测试代码 我也承认 我这个现在不好用)
> - 登录到抓说说的部分基本已经跑通了 tg的部分估计应该没怎么变
> - 增加了selenium的配置部分
> - 验证码登录是不是应该提上日程了
## 功能

* 自动登录空间, cv过验证
* 爬取说说文本
* 爬取说说图片
* 爬取说说转发
* QQ原生表情转文字
* 点赞(目前只支持`appid=311`, `typeid=0 or 5`的说说, 即原创和转发)
* 过滤部分广告(待测)
* 简单的tg机器人

(目前)不支持:

* 转原生表情(懒得搞.jpg)
* 爬取视频
* 给应用分享消息点赞
* 显示点赞人数和昵称
* 显示评论
* 评论
* 实时刷新
* webhook
* ....

目前有计划:

* 给任何消息点赞
* 实时(定时)刷新
* ~~webhook(可能会咕)~~

## 截图

> 等我有空的

## 需求

* 一台服务器
* 访问tg的网络环境, 以下二选一:
  * 你的服务器在国外
  * 你有可用的代理
* 一个开通了空间的QQ号
* 一个属于你的tg机器人, 得到token
* 取得你的用户ID(acceptID)

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
cp misc/example.yaml config.yaml
vim config.yaml     # 这里需要一个趁手的编辑器
# 填写qq, tg bot token, acceptId, 以及可选的代理
```

## 运行

### 简单开始

您只需:

1. 配置`qzone`条目下的`qq`项
2. 配置`bot`条目下的`token`项
3. 配置`bot`条目下的`accepted_id`项
4. 如果你使用代理, 还要配置`bot`条目下的`proxy`. 支持`http`, `socks5`, `socks5h`. 如果你的代理需要认证的话, 请一并参见下方链接:

[Working Behind a Proxy][1]
### 配置文件

配置文件在安装目录下的`config.yaml`

``` yaml
qzone:
  UA: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66
  cookie_expire: 9600
  fetch_times: 12
  log_level: 1
  password: 这里填密码
  qq: 这里填QQ
  savepwd: True
feed:
  keepdays: 3
selenium:
  browser: Edge # Chrome, Firefox, Edge is supported
  driver:
    executable_path: msedgedriver.exe # 最重要的ChromeOptions啥的还没适配 这个主要是填构造函数用的
bot:
  method: polling
  token: 这里填bot token
  accept_id:
  - 用户ID, 或是其他的chat id
  proxy:
    proxy_url: socks5 OR socks5h://URL_OF_THE_PROXY_SERVER:PROXY_PORT,
    # Optional, if you need authentication:
    urllib3_proxy_kwargs: 
      username: PROXY_USER
      password: PROXY_PASS
```
配置各项的含义请参考[wiki](https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3)
~~(有生之年系列)~~
### 将./src加入PYTHONPATH

唯一需要更改的是路径分隔符. [详见此处][2]
  - Unix系统, 请将`.env`文件中的`;`改为`:`. 
  - Windows系统无需更改. 

### 启动

``` shell
python3 src/main.py
#接下来输入你的密码
```

注意, 目前您的密码将在配置文件中无损失地存储. __脚本能够无需密钥地还原出您的密码, 您的管理员和攻击者也能够做到这一点.__ 请确保您主机或伺服器的安全性. 

> Update: 
> - 目前`savepwd`项默认为True. 但以任何形式无损失地保存密码都是不合适的, 所以等转发登陆二维码做成之后我想默认就不保存密码了

## 卸载

|directory  |description  |
|:----------|:------------|
|data       |用于缓存`keepdays`天内的feed|
|tmp        |本地保存cookie等|

脚本没有在Qzone2TG文件夹外存储数据. 

如果您需要完全卸载:
1. 删除clone的源文件夹, 在未被修改的情况下, 是`Qzone2TG`
2. _可选的_  删除安装的依赖:

    ``` shell
    #您可以自行选择卸载哪些扩展.
    pip3 uninstall python-telegram-bot python-telegram-bot[socks] selenium demjson lxml opencv-python
    ```

## Credits

@bufuchangfeng [qzone](https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py)

## License

[MIT License](https://github.com/JamzumSum/Qzone2TG/blob/master/LICENSE)

[1]: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Working-Behind-a-Proxy "Working Behind a Proxy"
[2]: https://code.visualstudio.com/docs/python/environments#_environment-variable-definitions-file "Use of the PYTHONPATH variable"