FROM python:3.11-slim as build

WORKDIR /home/build

# pack the package
COPY . ./
RUN bash src/zipapp.sh ./run

# ==============================================
#                 Runtime Stage
# ==============================================

FROM python:3.11-slim as release
# use slim since opencv-python doesn't offically support alpine.

LABEL org.opencontainers.image.source=https://github.com/aioqzone/Qzone2TG
LABEL org.opencontainers.image.description="Forward Qzone feeds to telegram."
LABEL org.opencontainers.image.licenses=AGPL-3.0-or-later

EXPOSE 80 88 443 8443
WORKDIR /app
ENV PATH="/app:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

COPY --from=build /home/build/run /app

ENTRYPOINT ["python", "app.pyz"]
