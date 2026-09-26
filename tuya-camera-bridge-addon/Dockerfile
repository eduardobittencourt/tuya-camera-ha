ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm
FROM golang:1.26-bookworm AS builder

WORKDIR /src
COPY bridge/ .
RUN go mod download && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /tuya-camera-bridge .

FROM bluenviron/mediamtx:1.21.1 AS mediamtx

FROM python:3.13-slim-bookworm AS pydeps
RUN pip install --no-cache-dir --no-deps --target=/deps tuya-mobile==1.2.0

FROM ${BUILD_FROM}

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg python3-aiohttp python3-cryptography \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /tuya-camera-bridge /usr/local/bin/tuya-camera-bridge
COPY --from=mediamtx /mediamtx /usr/local/bin/mediamtx
COPY --from=pydeps /deps /usr/local/lib/python3.11/dist-packages
COPY app/addon_app.py /usr/local/bin/tuya-camera-addon
COPY run.sh /run.sh
RUN chmod 0755 /run.sh /usr/local/bin/tuya-camera-addon

CMD ["/run.sh"]
