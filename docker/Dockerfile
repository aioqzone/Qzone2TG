FROM nikolaik/python-nodejs:python3.11-nodejs18-slim as build

WORKDIR /home/pn/app

# pack the package
COPY . ./
RUN npm install --omit optional --omit dev --no-fund \
    && mkdir ./run \
    && mv ./node_modules ./run
RUN sh src/zipapp.sh ./run

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.11-slim as release
# use slim since opencv-python doesn't offically support alpine.

LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG
LABEL org.opencontainers.image.description="Forward Qzone feeds to telegram."
LABEL org.opencontainers.image.licenses=AGPL-3.0-or-later

EXPOSE 80 88 443 8443
WORKDIR /app
ENV PATH="/app:$PATH"
# ENV PYTHONPATH="/app:$PYTHONPATH"

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        curl \
        fontconfig \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install --no-install-recommends -y \
        nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /home/pn/app/run /app

ENTRYPOINT ["python", "app.pyz"]
