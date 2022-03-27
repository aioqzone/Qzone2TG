# Qzone3TG

Forward Qzone feeds to telegram.

> Warning: Qzone3TG is still under active development. Features and configurations may be changed in future releases.

[简体中文](README.zh-CN.md)

## Deploy

> No official image has been released now. You might build one on your own.

Build and startup docker image:

``` sh
docker build -f docker/Dockerfile --network host -t qzone3tg:latest .
docker-compose -f docker/docker-compose.yml up -d
```

## Config

> See: [Quick Start](https://jamzumsum.github.io/Qzone2TG/quickstart.html#id3)

Qzone3TG uses [pydantic](https://pydantic-docs.helpmanual.io/usage/settings) to manage user settings. YAML config file (like that in v2) and environment variables are supported. See [config/test.yml](config/test.yml) for the minimal and maximal config examples.

Since environment variable style configuration is fully supported, one can merge configs into `docker-compose.yml`. See [docker/docker-compose.yml](docker/docker-compose.yml) for an example.

## Documents and Tutorials

- [Qzone3TG Documents](https://jamzumsum.github.io/Qzone2TG)
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
