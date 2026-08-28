# IT Guardian Windows Agent

The v0.7 Windows Agent is a non-interactive managed endpoint binary. It enrolls once through the administrative Gateway, stores the device private key protected with Windows DPAPI LocalMachine, then communicates only with Device Edge over mTLS.

## Supported v0.7 target

- Windows 10/11 modern x64; arm64 is compile-gated in CI.
- Windows 7/8/8.1 remain a separate legacy capability matrix and do not define the v0.7 stable gate.
- No arbitrary remote shell exists. Commands are limited to `inventory.refresh`, `device.reboot` and `service.restart` with local schema validation.

## Files

Default data directory: `C:\ProgramData\ITGuardian\Agent`.

- `agent.json`: non-secret runtime configuration.
- `device-edge-ca.pem`: public CA that authenticates the Device Edge HTTPS server.
- `identity.json`: device IDs, certificate/CA chain, session ID and DPAPI-protected private key.
- `spool\`: bounded crash-safe offline queue.
- `update-healthy`: health marker used by the signed updater rollback state machine.

The one-time enrollment token is accepted only on the `enroll` command line and is never written to `agent.json` or `identity.json`.

## Enrollment

1. Install the MSI. The service is registered as `ITGuardianAgent` under `NT AUTHORITY\LocalService`; it is delayed-auto but is not started by the MSI.
2. Place the Device Edge public server CA at `C:\ProgramData\ITGuardian\Agent\device-edge-ca.pem`.
3. Create `agent.json` from `agent.example.json` and set the real Device Edge URL.
4. Create an enrollment token from IT Guardian for the target asset.
5. From an elevated terminal execute once:

```powershell
& 'C:\Program Files\IT Guardian\itguardian-agent.exe' enroll `
  --gateway https://guardian.example.com `
  --token '<ONE_TIME_TOKEN>' `
  --state 'C:\ProgramData\ITGuardian\Agent\identity.json'
```

The agent generates an ECDSA P-256 private key locally, sends only its CSR, validates the returned certificate chain/SPIFFE identity/serial/fingerprint, protects the private key with DPAPI LocalMachine and persists only protected identity state.

Then start the service:

```powershell
Start-Service ITGuardianAgent
Get-Service ITGuardianAgent
```

## Runtime

The installed service executes:

```text
itguardian-agent.exe run --config C:\ProgramData\ITGuardian\Agent\agent.json
```

Runtime flow:

```text
DPAPI identity
  -> mTLS Device Edge
  -> heartbeat/capabilities
  -> CPU/RAM/disk telemetry
  -> typed command acquire
  -> running
  -> native WinAPI/SCM execution
  -> idempotent terminal result
  -> offline spool/retry when required
```

The agent performs an initial real endpoint cycle before writing `update-healthy`. A network failure is never treated as successful health.

## Offline behavior

- 64 MiB maximum spool.
- 10,000 item maximum.
- Command terminal results have priority over telemetry.
- Stable IDs prevent payload mutation under retry.
- Backoff starts at one second, grows exponentially with jitter and is capped at five minutes.
- A command is not executed again merely because upload of its terminal result failed.

## Updates

The updater library verifies an Ed25519-signed canonical manifest, HTTPS URL, expected size and streaming SHA-256 before activation. Downgrades are rejected. Activation keeps the previous binary until the new process writes the health marker; timeout causes atomic rollback.

Update transport/catalog publication is intentionally independent of command execution; no `shell.exec` or unsigned binary install command exists.

## Build verification

```powershell
go test ./...
go build -trimpath -o dist\itguardian-agent.exe .\cmd\itguardian-agent
```

The GitHub Actions release gate additionally builds arm64, creates the WiX v4 MSI, publishes SHA-256 hashes, scans source for forbidden insecure TLS/arbitrary-shell patterns and runs the v0.7 integration gate before release promotion.
