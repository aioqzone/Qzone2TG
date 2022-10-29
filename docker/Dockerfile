FROM python:3.11-slim as build

LABEL org.opencontainers.image.url=https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg
LABEL org.opencontainers.image.documentation=https://aioqzone.github.io/Qzone2TG
LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        git \
        curl \
    && curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install --no-install-recommends -y \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

# since we use pip to pack pyz, the poetry install step can be removed.
COPY . /app
WORKDIR /app

# package the package
RUN python src/pack.py . --clean

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.11-slim as release
# use slim since opencv-python doesn't offically support alpine.

EXPOSE 80 88 443 8443
ENV PATH="/app:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        curl \
        fontconfig \
    && curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install --no-install-recommends -y \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/run /app
WORKDIR /app

ENTRYPOINT ["python", "app.pyz"]
