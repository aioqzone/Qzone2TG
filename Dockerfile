FROM python:3.9 as build

COPY . /app

WORKDIR /app

RUN apt-get update -y && apt-get install -y gnome-keyring && \
    pip install -e .\[socks\]

FROM python:3.9-alpine

COPY --from=build /app /app
COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

WORKDIR /app

RUN apk add nodejs

VOLUME ["/app/config", "/app/data"]
EXPOSE 80 88 443 8443

ENTRYPOINT python src/__main__.py --no-interaction
