FROM python:3.9 as build

COPY . /app

WORKDIR /app

RUN pip install -e .
RUN pip install python-telegram-bot[socks]

FROM python:3.9-alpine

COPY --from=build /app /app
COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

WORKDIR /app

CMD python src/__main__.py
