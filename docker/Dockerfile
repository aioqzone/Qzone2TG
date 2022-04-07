FROM python:3.10-slim as build

LABEL org.opencontainers.image.url=https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg
LABEL org.opencontainers.image.documentation=https://aioqzone.github.io/Qzone2TG
LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG

COPY . /app
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        git \
        curl \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install

# install and configure poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && $HOME/.local/bin/poetry config virtualenvs.create true \
    && $HOME/.local/bin/poetry config virtualenvs.in-project true

ENV PATH=/root/.local/bin:$PATH

# package the package
RUN python src/pack.py -p "python" --clean

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.10-slim as release
# use slim since opencv-python doesn't offically support alpine.

COPY --from=build /app/run /app
COPY --from=build /app/node_modules /app/
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 80 88 443 8443

ENTRYPOINT ["./app.pyz"]
