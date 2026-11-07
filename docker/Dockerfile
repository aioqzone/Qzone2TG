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

WORKDIR /app
ENV PATH="/app:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"
ENV TZ="Asia/Shanghai"

COPY --from=build /home/build/run /app

ENTRYPOINT ["python", "app.pyz"]
