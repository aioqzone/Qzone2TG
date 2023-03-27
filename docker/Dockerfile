FROM nikolaik/python-nodejs:python3.11-nodejs18-alpine as build

USER pn
WORKDIR /home/pn/app

COPY . ./run/

# pack the dependencies
RUN bash src/zipapp.sh ./run \
    && npm install --omit optional --omit dev --no-fund \
    && mv ./node_modules ./run/

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.11-alpine as release

LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG
LABEL org.opencontainers.image.description="Forward Qzone feeds to telegram."
LABEL org.opencontainers.image.licenses=AGPL-3.0-or-later

WORKDIR /app
EXPOSE 80 88 443 8443
ENV PATH="/app:$PATH"
# ENV PYTHONPATH="/app:$PYTHONPATH"

# we do not need npm in runtime stage
RUN apk add --no-cache \
    fontconfig \
    nodejs

COPY --from=build /home/pn/app/run ./

ENTRYPOINT ["python", "app.pyz"]
