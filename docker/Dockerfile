FROM python:3.10 as build

LABEL org.opencontainers.image.url=https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg
LABEL org.opencontainers.image.documentation=https://aioqzone.github.io/Qzone2TG
LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG

COPY . /app
WORKDIR /app

RUN curl -sSL https://install.python-poetry.org | python3 - \
    && $HOME/.local/bin/poetry config virtualenvs.create true \
    && $HOME/.local/bin/poetry config virtualenvs.in-project true \
    && $HOME/.local/bin/poetry install --no-dev --no-interaction --no-root \
    && $HOME/.local/bin/poetry build -f wheel \
    && $HOME/.local/bin/poetry run pip install dist/*.whl

# ==============================================

FROM python:3.10-slim as release
# use slim since opencv-python doesn't offically support alpine.
# Though copying the built opencv does work, but cryptography cannot work with this method.

COPY --from=build /app/.venv /venv
COPY package.json /app
WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y \
    nodejs \
    && npm install \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 80 88 443 8443
ENV PATH=/venv/bin:$PATH

ENTRYPOINT ["python", "-m", "qzone3tg"]
