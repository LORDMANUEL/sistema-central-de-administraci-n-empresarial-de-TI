# IT Guardian Device Edge

`device-edge-service` is the v0.7 endpoint boundary. It terminates device mTLS, derives the authoritative tenant/asset/device principal from the verified Guardian SPIFFE certificate, checks the signed PKI CRL and proxies only the five allowlisted v0.6 device operations.

## Security contract

- TLS 1.2 or newer and a verified client certificate are mandatory.
- Client-supplied `X-Guardian-*`, `Forwarded` and `X-Forwarded-*` identity data are never trusted; the proxy creates trusted headers from the certificate.
- Only heartbeat, command acquire/running/result and telemetry POST routes are exposed.
- The service starts only after loading a signed current CRL and fails closed once the last-good CRL expires.
- The Device Edge consumes only public CA chain/CRL data from PKI. CA private keys and Identity/Enrollment signing keys must never be mounted into this container.
- `DEVICE_PROXY_SHARED_SECRET` is server-side only and must match the v0.6 Agent Control, Command and Telemetry trusted proxy secret.

## Required environment

| Variable | Required | Default |
|---|---:|---|
| `DEVICE_EDGE_TLS_CERT_FILE` | yes | - |
| `DEVICE_EDGE_TLS_KEY_FILE` | yes | - |
| `DEVICE_PROXY_SHARED_SECRET` | yes | - |
| `DEVICE_EDGE_LISTEN_ADDR` | no | `:8443` |
| `DEVICE_EDGE_CA_CHAIN_URL` | no | `http://pki-service:8004/api/v1/ca/chain` |
| `DEVICE_EDGE_CRL_URL` | no | `http://pki-service:8004/api/v1/ca/crl` |
| `DEVICE_EDGE_CRL_REFRESH_SECONDS` | no | `300` |
| `AGENT_CONTROL_SERVICE_URL` | no | `http://agent-control-service:8007` |
| `COMMAND_SERVICE_URL` | no | `http://command-service:8008` |
| `TELEMETRY_SERVICE_URL` | no | `http://telemetry-service:8009` |
| `DEVICE_EDGE_MAX_BODY_BYTES` | no | `262144` |

The TLS server certificate/key authenticate the Device Edge to agents. They are independent from the PKI device CA private material. Production should issue the server certificate from the organization's normal server TLS trust path and distribute only its public CA certificate to the Windows Agent.

## Routes

- `POST /api/v1/device/heartbeat`
- `POST /api/v1/device/commands/acquire`
- `POST /api/v1/device/commands/{uuid}/running`
- `POST /api/v1/device/commands/{uuid}/result`
- `POST /api/v1/device/telemetry`

`GET /health/live` and `GET /health/ready` exist inside the same mTLS listener. Readiness additionally requires a current signed CRL.

## Development verification

```bash
go test ./...
go vet ./...
go build ./cmd/device-edge
docker build -t itguardian-device-edge:dev .
```
