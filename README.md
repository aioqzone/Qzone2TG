# Qzone2TG

爬取QQ空间说说并转发到telegram

> 随缘修BUG</br>
> [Project board](https://github.com/JamzumSum/Qzone2TG/projects/2)</br>
> 目前是一个能用的版本

## 功能

* 自动登录空间, ~~cv过验证~~
* 二维码登录
* 爬取说说文本
* 爬取说说图片
* 爬取说说转发
* 点赞(应用消息的点赞受限)
* 过滤部分广告(待测)
* 简单的tg机器人, 支持webhook

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

请确保安装了`git`, `python3.8+`和对应的`pip`及`setuptools`.

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

### 配置文件

应用的配置文件在`config`目录下的`config.yaml`. 配置文件示例在`misc`目录下的`example.yaml`.

配置各项的含义请参考[wiki][3]

### PYTHONPATH

源码存储于`src`下, 必须确保它加入了`PYTHONPATH`, 否则无法确保正确运行.

默认的设置适用于Windows系统. Unix系统, 请将`.env`文件中的`;`改为`:`. ([详见此处][2])

### 启动

``` shell
python3 src/main.py
# 输入密码或跳过
```

注意, 当允许保存密码时, 您的密码将在配置文件中无损失地存储. __脚本能够无需密钥地还原出您的密码, 您的管理员和攻击者也能够做到这一点.__ 请确保您主机或伺服器的安全性. 
因此 __强烈建议__ 不保存密码, 即在配置文件中保持`savepwd`为`False`(默认).

注意, 如果您的存储不安全, 攻击者可能通过缓存的cookie __直接操作您的QQ空间__. 

## 卸载

|data directory |description  |
|:--------------|:------------|
|data           |用于缓存`keepdays`天内的feed|
|tmp            |本地保存cookie等|

脚本没有在Qzone2TG文件夹外存储数据. 

如果您需要完全卸载:
1. 删除clone的源文件夹, 在未被修改的情况下, 是`Qzone2TG`
2. _可选的_  删除安装的依赖:

    ``` shell
    #您可以自行选择卸载哪些扩展.
    pip3 uninstall python-telegram-bot lxml opencv-python omegaconf tencentlogin
    ```

## Credits

@bufuchangfeng [qzone](https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py)

Other dependencies: [Dependency Graph](https://github.com/JamzumSum/Qzone2TG/network/dependencies#setup.py)

## License

- [AGPL-3.0](https://github.com/JamzumSum/Qzone2TG/blob/master/LICENSE)
- __不鼓励、不支持一切商业使用__

[1]: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Working-Behind-a-Proxy "Working Behind a Proxy"
[2]: https://code.visualstudio.com/docs/python/environments#_environment-variable-definitions-file "Use of the PYTHONPATH variable"
[3]: https://github.com/JamzumSum/Qzone2TG/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E6%A1%A3 "配置文件"
