FROM python:3.9-alpine as build

COPY . /app

WORKDIR /app

RUN apk add gcc musl-dev python3-dev libffi-dev openssl-dev cargo && \
    pip install -U pip && pip install .\[socks\]

# ==============================================

FROM python:3.9-alpine

COPY --from=build /app /app
COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

WORKDIR /app

RUN apk add nodejs gnome-keyring

EXPOSE 80 88 443 8443

ENV PYTHONPATH src
ENV DBUS_SESSION_BUS_ADDRESS unix:path=/run/user/0/bus

ENTRYPOINT python src/qzone2tg --no-interaction
