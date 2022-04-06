FROM python:3.10 as build

LABEL org.opencontainers.image.url=https://github.com/aioqzone/Qzone2TG/pkgs/container/qzone3tg
LABEL org.opencontainers.image.documentation=https://aioqzone.github.io/Qzone2TG
LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG

COPY . /app
WORKDIR /app

# install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH=/root/.local/bin:$PATH
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project true

# install package
RUN poetry install --no-dev --no-root
RUN poetry run pip install .

# ==============================================

FROM python:3.10-slim as release
# use slim since opencv-python doesn't offically support alpine.
# Though copying the built opencv does work, but cryptography cannot work with this method.

COPY --from=build /app/.venv /venv
COPY package.json /app/
WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install

EXPOSE 80 88 443 8443
ENV PATH=/venv/bin:$PATH

ENTRYPOINT ["python", "-m", "qzone3tg"]
