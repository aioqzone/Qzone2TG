FROM python:3.10-slim as build

LABEL org.opencontainers.image.url=https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg
LABEL org.opencontainers.image.documentation=https://aioqzone.github.io/Qzone2TG
LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        git \
        curl \
    && curl -fsSL https://deb.nodesource.com/setup_17.x | bash - \
    && apt-get install --no-install-recommends -y \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

# install and configure poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && $HOME/.local/bin/poetry config virtualenvs.create true \
    && $HOME/.local/bin/poetry config virtualenvs.in-project true

ENV PATH="/root/.local/bin:$PATH"

COPY . /app
WORKDIR /app

# package the package
RUN python src/pack.py . --clean

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.10-slim as release
# use slim since opencv-python doesn't offically support alpine.

EXPOSE 80 88 443 8443
ENV PATH="/app:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"
# ENV FONTCONFIG_PATH="/etc/fonts"

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        curl \
        fontconfig \
    && curl -fsSL https://deb.nodesource.com/setup_17.x | bash - \
    && apt-get install --no-install-recommends -y \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/run /app
WORKDIR /app

ENTRYPOINT ["python", "app.pyz"]
