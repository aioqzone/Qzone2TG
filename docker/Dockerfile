FROM python:3.15-slim AS build

# uv is only needed while building; it is not copied to the runtime stage.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never
# Allow zipapp.sh to install a build toolchain only if some dependency needs compiling.
ENV INSTALL_BUILD_TOOLS=1

WORKDIR /home/build

# pack the package
COPY . ./
RUN bash src/zipapp.sh ./run

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.15-slim AS release
# use slim since opencv-python doesn't offically support alpine.
# No build toolchain is copied into this stage: only the packed app is.

LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG
LABEL org.opencontainers.image.description="Forward Qzone feeds to telegram."
LABEL org.opencontainers.image.licenses=AGPL-3.0-or-later

# Run unprivileged by default. If the container is started as root instead
# (``--user root``), the entrypoint repairs the ownership of the mounted
# volumes and then drops the privileges to this user.
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "${APP_GID}" qzone \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home \
        --home-dir /home/qzone --shell /bin/false qzone

WORKDIR /app
ENV PATH="/app:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"
ENV TZ="Asia/Shanghai"
ENV HOME="/home/qzone"

COPY --from=build /home/build/run /app

# Writable mount points. /app itself stays owned by root so the application
# code cannot be modified by the app user. A fresh named volume mounted here
# inherits this ownership from the image, so it works without a host chown.
RUN mkdir -p /app/log /app/data \
    && chown qzone:qzone /app/log /app/data

COPY src/docker_entrypoint.py /entrypoint.py

USER qzone

ENTRYPOINT ["python", "/entrypoint.py"]
