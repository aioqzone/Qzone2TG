# Qzone2TG

爬取QQ空间说说并转发到telegram

> 随缘修BUG
> [Project board](https://github.com/JamzumSum/Qzone2TG/projects/2)

## 功能

* 自动登录空间, cv过验证
* 爬取说说文本
* 爬取说说图片
* 爬取说说转发
* QQ原生表情转文字
* 点赞(目前只支持`appid=311`, `typeid=0 or 5`的说说, 即原创和转发)
* 过滤部分广告(待测)
* 简单的tg机器人

## 截图

> 咕咕咕

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

``` shell
# clone本项目
git clone https://github.com/JamzumSum/Qzone2TG.git
cd Qzone2TG

# 安装依赖
pip install -e .

# 建立配置文档. 
# Update: 请务必参看下方的配置文件说明
mkdir config
cp misc/example.yaml config/config.yaml

vim config.yaml     # 这里需要一个趁手的编辑器
# 填写qq, tg bot token, acceptId以及可选的代理, 设置selenium
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

应用的配置文件在`config`目录下的`config.yaml`. 配置文件示例在`misc`目录下的`example.yaml`.

配置各项的含义请参考[wiki](https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3)
~~(有生之年系列)~~

### PYTHONPATH

源码存储于`src`下, 必须确保它加入了`PYTHONPATH`, 否则无法找到包.

默认的设置适用于Windows系统. Unix系统, 请将`.env`文件中的`;`改为`:`. ([详见此处][2])

### 启动

``` shell
python3 src/main.py
#接下来输入你的密码
```

注意, 目前您的密码将在配置文件中无损失地存储. __脚本能够无需密钥地还原出您的密码, 您的管理员和攻击者也能够做到这一点.__ 请确保您主机或伺服器的安全性. 
注意, 如果您的存储不安全, 攻击者可能通过缓存的cookie __直接操作您的QQ空间__. 

> Update: 
> - 目前`savepwd`项默认为True. 还是等等二维码登录吧

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
