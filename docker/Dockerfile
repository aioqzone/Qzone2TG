FROM python:3.9 as build

COPY . /app

WORKDIR /app

RUN pip install -U pip && pip install .

# ==============================================

FROM python:3.9-slim
# use slim since opencv-python doesn't offically support alpine.
# Though copying the built opencv does work, but cryptography cannot work with this method.

COPY --from=build /app /app
COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y nodejs

EXPOSE 80 88 443 8443

ENV PYTHONPATH src

ENTRYPOINT ["python", "src/qzone2tg"]
