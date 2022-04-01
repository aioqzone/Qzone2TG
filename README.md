# Qzone3TG

Forward Qzone feeds to telegram.

[![Dev CI](https://github.com/JamzumSum/Qzone2TG/actions/workflows/ci.yml/badge.svg?branch=v3%2Fdev)](https://github.com/JamzumSum/Qzone2TG/actions/workflows/ci.yml)
[![Sphinx](https://img.shields.io/github/workflow/status/JamzumSum/Qzone2TG/pages%20build%20and%20deployment/gh-pages?label=Sphinx&logo=github)][doc]
[![ghcr.io](https://img.shields.io/github/workflow/status/JamzumSum/Qzone2TG/Build%20Docker%20Image?label=ghcr.io&logo=docker)][ghcr]

> Warning: Qzone3TG is still under active development. Features and configurations may be changed in future releases.

[简体中文](README.zh-cn.md)

## Deploy

We support and only support docker deployment. Currently we have published our pre-built images
to [ghcr.io][ghcr].

``` sh
# you may save a copy of this file and modify it.
docker-compose -f docker/docker-compose.yml up -d
```

> If you'd like build a image by yourself, see documentation: [build](https://jamzumsum.github.io/Qzone2TG/build.html#docker)

## Config

> See: [Quick Start](https://jamzumsum.github.io/Qzone2TG/quickstart.html#id3)

Qzone3TG uses [pydantic](https://pydantic-docs.helpmanual.io/usage/settings) to manage user settings. YAML config file (like that in v2) and environment variables are supported. See [config/test.yml](config/test.yml) for the minimal and maximal config examples.

Since environment variable style configuration is fully supported, one can merge configs into `docker-compose.yml`. See [docker/docker-compose.yml](docker/docker-compose.yml) for an example.

## Documents and Tutorials

- [Qzone3TG Documents][doc]
- Author's blog: [Qzone3TG Topic](https://zzsblog.top/Products/Qzone3TG/index.html)

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


[doc]: https://jamzumsum.github.io/Qzone2TG
[ghcr]: https://github.com/JamzumSum/Qzone2TG/pkgs/container/qzone3tg/latest
