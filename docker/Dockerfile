FROM python:3.9 as build

COPY . /app
WORKDIR /app

RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
RUN apt-get update && pip install --no-cache-dir .

# ==============================================

FROM python:3.9-slim as release
# use slim since opencv-python doesn't offically support alpine.
# Though copying the built opencv does work, but cryptography cannot work with this method.

COPY --from=build /venv /venv

RUN apt-get update && apt-get install --no-install-recommends -y \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
EXPOSE 80 88 443 8443
ENV PATH=/venv/bin:$PATH

ENTRYPOINT ["python", "-m", "qzone3tg"]
