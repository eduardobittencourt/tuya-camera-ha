ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm
FROM golang:1.26-bookworm AS builder

WORKDIR /src
COPY bridge/ .
RUN go mod download && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /tuya-camera-bridge .

FROM ${BUILD_FROM}

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /tuya-camera-bridge /usr/local/bin/tuya-camera-bridge
COPY run.sh /run.sh
RUN chmod 0755 /run.sh

CMD ["/run.sh"]
