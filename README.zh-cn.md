# Qzone3TG

转发说说到 Telegram.

[![Dev CI](https://github.com/aioqzone/Qzone2TG/actions/workflows/ci.yml/badge.svg?branch=v3%2Fdev)](https://github.com/aioqzone/Qzone2TG/actions/workflows/ci.yml)
[![Sphinx](https://img.shields.io/github/workflow/status/aioqzone/Qzone2TG/pages%20build%20and%20deployment/gh-pages?label=Sphinx&logo=github)][doc]
[![ghcr.io](https://img.shields.io/github/workflow/status/aioqzone/Qzone2TG/Build%20Docker%20Image?label=ghcr.io&logo=docker)][ghcr]
[![channel](https://img.shields.io/badge/dynamic/xml?label=Channel&query=%2F%2Fdiv%5B%40class%3D%22tgme_page_extra%22%5D&url=https%3A%2F%2Ft.me%2Fqzone2tg&style=social&logo=telegram)](https://t.me/qzone2tg)

> 1. ⚠️ Qzone3TG 仍在开发阶段，任何功能和配置项都有可能在未来的版本中发生变化。
> 2. 🆘 **欢迎有意协助开发/维护的中文开发者**。范围包括 [aioqzone][org] 组织拥有的所有仓库。

[English](README.md)

## 部署

我们仅支持 docker 部署。目前我们在 [ghcr.io][ghcr] 发布了镜像。

``` sh
# 或许您应该复制一份文件，并对其中的配置做一些修改。
docker-compose -f docker/docker-compose.yml up -d
```

> 如果您想要自行构建镜像，请查看文档：[build](https://aioqzone.github.io/Qzone2TG/build.html#docker)

## 配置

> 文档：[快速上手](https://aioqzone.github.io/Qzone2TG/quickstart.html#id3)

Qzone3TG 使用 [pydantic](https://pydantic-docs.helpmanual.io/usage/settings) 管理用户配置。我们同时支持 yaml 文件配置（和v2几乎一致）和环境变量配置。前往 [config/test.yml](config/test.yml) 查看最小配置和最大（全）配置。

得益于我们支持从环境变量中读取配置，您可以把不太复杂的配置文件直接写入 `docker-compose.yml` 的环境变量部分。[docker/docker-compose.yml](docker/docker-compose.yml) 为您提供了范例。

## 文档和教程

- [Qzone3TG 文档][doc]
- 博客专题: [Qzone3TG Topic](https://zzsblog.top/Products/Qzone3TG/index.html)

> 您可以在我们的 [讨论群](https://t.me/qzone2tg_discuss) 寻求帮助。

## License

```
Copyright (C) 2021-2022 aioqzone

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


[doc]: https://aioqzone.github.io/Qzone2TG
[ghcr]: https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg/latest
[org]: https://github.com/orgs/aioqzone/repositories
