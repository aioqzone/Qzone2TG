# Qzone3TG

Forward Qzone feeds to telegram.

[![Sphinx](https://img.shields.io/github/actions/workflow/status/aioqzone/Qzone2TG/sphinx.yml?label=Sphinx&logo=github)][doc]
[![ghcr.io](https://img.shields.io/github/actions/workflow/status/aioqzone/Qzone2TG/docker.yml?label=ghcr.io&logo=docker)][ghcr]
[![channel](https://img.shields.io/badge/dynamic/xml?label=Channel&query=%2F%2Fdiv%5B%40class%3D%22tgme_page_extra%22%5D&url=https%3A%2F%2Ft.me%2Fqzone2tg&style=social&logo=telegram)](https://t.me/qzone2tg)

> 1. ⚠️ Qzone3TG is still under active development. Features and configurations may be changed in future releases.

[简体中文](README.zh-cn.md)

## Deployment

We support and only support docker deployment. Currently we have published our pre-built image
to [ghcr.io][ghcr].

``` sh
# you may save a copy of this file and modify it.
docker-compose -f docker/docker-compose.yml up -d
```

> If you'd like build a image by yourself, see documentation: [build](https://aioqzone.github.io/Qzone2TG/build.html#docker)

## Configuration

> See: [Quick Start](https://aioqzone.github.io/Qzone2TG/quickstart.html#id3)

Qzone3TG uses [pydantic](https://pydantic-docs.helpmanual.io/usage/settings) to manage user settings. YAML config file (like that in v2) and environment variables are __both__ supported. See [config/test.yml](config/test.yml) for an example of (the minimal and maximal) configurations.

Since environment variable style configuration is fully supported, one can merge configs into `docker-compose.yml`. See [docker/docker-compose.yml](docker/docker-compose.yml) for an example.

## Documentations and Tutorials

- [Qzone3TG Documents][doc]
- Author's blog: [Qzone3TG Topic](https://zzsblog.top/Products/Qzone3TG/index.html)

> You can look for help at our [discussion group](https://t.me/qzone2tg_discuss).

## License

```
Copyright (C) 2021-2023 aioqzone

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

- Qzone2TG is an aioqzone application and respects aioqzone's [disclaimer](https://aioqzone.github.io/aioqzone/disclaimers.html) if it has no conflict with our User Agreement.
- Users should accept our [User Agreement](https://aioqzone.github.io/Qzone2TG/agreement.html) before using Qzone2TG.

[doc]: https://aioqzone.github.io/Qzone2TG
[ghcr]: https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg/latest
