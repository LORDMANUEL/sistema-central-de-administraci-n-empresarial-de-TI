# syntax=docker/dockerfile:1.7
FROM golang:1.23-alpine AS build
ARG TARGETARCH=amd64
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/device-edge ./cmd/device-edge

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/device-edge /device-edge
USER nonroot:nonroot
EXPOSE 8443
ENTRYPOINT ["/device-edge"]
