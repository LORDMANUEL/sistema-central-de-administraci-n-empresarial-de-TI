# syntax=docker/dockerfile:1.7
FROM golang:1.23-alpine AS build
ARG TARGETARCH=amd64
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/device-edge ./cmd/device-edge \
    && mkdir -p /out/device-edge-ca /out/device-edge-tls

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/device-edge /device-edge
COPY --chown=nonroot:nonroot --from=build /out/device-edge-ca /var/lib/guardian/device-edge-ca
COPY --chown=nonroot:nonroot --from=build /out/device-edge-tls /var/lib/guardian/device-edge-tls
USER nonroot:nonroot
EXPOSE 8443
ENTRYPOINT ["/device-edge"]
