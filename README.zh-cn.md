# Qzone3TG

转发说说到 Telegram.

> 注意：Qzone3TG 仍在开发阶段，任何功能和配置项都有可能在未来的版本中发生变化。

[English](README.md)

## 部署

> 目前还没有发布官方构建镜像。您可能需要自己构建 docker 镜像。

构建 & 启动:

``` sh
docker build -f docker/Dockerfile --network host -t qzone3tg:latest .
docker-compose -f docker/docker-compose.yml up -d
```

## 配置

> 文档：[快速上手](https://jamzumsum.github.io/Qzone2TG/quickstart.html#id3)

Qzone3TG 使用 [pydantic](https://pydantic-docs.helpmanual.io/usage/settings) 管理用户配置。我们同时支持 yaml 文件配置（和v2几乎一致）和环境变量配置。前往 [config/test.yml](config/test.yml) 查看最小配置和最大（全）配置。

得益于我们支持从环境变量中读取配置，您可以把不太复杂的配置文件直接写入 `docker-compose.yml` 的环境变量部分。[docker/docker-compose.yml](docker/docker-compose.yml) 为您提供了范例。

## 文档和教程

- [Qzone3TG 文档](https://jamzumsum.github.io/Qzone2TG)
- 博客专题: [Qzone3TG Topic](https://zzsblog.top/Products/Qzone3TG/index.html)

## License

```
Copyright (C) 2021-2022 JamzumSum

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
