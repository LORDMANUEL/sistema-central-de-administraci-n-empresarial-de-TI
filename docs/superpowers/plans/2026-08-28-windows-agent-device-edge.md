# IT Guardian v0.7.0 Windows Agent + Device Edge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar un Windows Agent moderno que use certificados reales y un Device Edge mTLS para operar de punta a punta contra el core v0.6 sin confiar en headers controlados por el endpoint.

**Architecture:** Dos binarios Go separados. `device-edge-service` termina mTLS, deriva el principal desde el URI SAN SPIFFE y hace proxy solo a cinco rutas allowlisted. `windows-agent` genera y protege identidad local, enrola por Gateway, usa mTLS para heartbeat/telemetry/commands y mantiene spool/updater local.

**Tech Stack:** Go 1.23+, Windows x64/arm64, `golang.org/x/sys/windows` para DPAPI/SCM/telemetry de plataforma, TLS/X.509 estándar, Ed25519/SHA-256 estándar, Docker para Device Edge, WiX v4 en runner Windows para MSI.

**Spec:** `docs/superpowers/specs/2026-08-28-windows-agent-device-edge-design.md`

## Global Constraints

- `main` v0.6.0 es la base y no se modifica directamente.
- No existe shell remoto arbitrario.
- La identidad del dispositivo deriva del certificado X.509 validado, nunca de headers del cliente.
- La private key del dispositivo no sale del endpoint.
- El agente no puede desactivar verificación TLS.
- Los contratos HTTP de Agent Control, Command y Telemetry v0.6 se mantienen sin cambios incompatibles.
- La promoción de `VERSION` a `0.7.0` ocurre únicamente después de CI/E2E verde sobre el mismo SHA candidato.

---

### Task 1: Device identity parser and route allowlist

**Files:**
- Create: `services/device-edge-service/go.mod`
- Create: `services/device-edge-service/internal/identity/identity_test.go`
- Create: `services/device-edge-service/internal/identity/identity.go`
- Create: `services/device-edge-service/internal/routes/routes_test.go`
- Create: `services/device-edge-service/internal/routes/routes.go`

**Interfaces:**
- Produces: `identity.FromCertificate(*x509.Certificate) (Principal, error)` with UUID strings and certificate serial.
- Produces: `routes.Match(method, path) (Target, bool)` where Target has upstream kind and path.

- [ ] **Step 1: Write RED identity tests** for exactly one Guardian SPIFFE URI SAN, malformed UUID, duplicate Guardian SAN and missing SAN.
- [ ] **Step 2: Run** `cd services/device-edge-service && go test ./internal/identity -v`; expected FAIL because parser is absent.
- [ ] **Step 3: Implement minimal parser** using `net/url`, exact path segments `tenant/<uuid>/asset/<uuid>/device/<uuid>`, `google/uuid`-free validation via `encoding/hex`/format helper or `github.com/google/uuid` pinned if chosen.
- [ ] **Step 4: Run identity tests**; expected PASS.
- [ ] **Step 5: Write RED route tests** proving only the five device routes match and admin/catch-all paths do not.
- [ ] **Step 6: Run route tests**; expected FAIL because matcher is absent.
- [ ] **Step 7: Implement static matcher** with exact methods and UUID validation for command path IDs.
- [ ] **Step 8: Run** `go test ./...`; expected PASS.
- [ ] **Step 9: Commit** `feat: add device certificate identity and route allowlist`.

### Task 2: Device Edge mTLS proxy and CRL

**Files:**
- Create: `services/device-edge-service/internal/proxy/proxy_test.go`
- Create: `services/device-edge-service/internal/proxy/proxy.go`
- Create: `services/device-edge-service/internal/revocation/crl_test.go`
- Create: `services/device-edge-service/internal/revocation/crl.go`
- Create: `services/device-edge-service/cmd/device-edge/main.go`
- Create: `services/device-edge-service/Dockerfile`
- Create: `services/device-edge-service/.dockerignore`
- Create: `services/device-edge-service/README.md`

**Interfaces:**
- Consumes: `identity.FromCertificate`, `routes.Match`.
- Produces: HTTPS server requiring verified client certificate; injected trusted headers only after validation.

- [ ] **Step 1: Write RED proxy tests** with `httptest`: client-supplied `X-Guardian-*` and forwarding headers are removed; certificate-derived values and proxy token are injected; unallowlisted route returns 404; upstream cannot be selected by request data.
- [ ] **Step 2: Run proxy tests**; expected FAIL because handler is absent.
- [ ] **Step 3: Implement handler** with body cap, hop-by-hop/header stripping, request ID pass-through/generation and fixed upstream URLs from env.
- [ ] **Step 4: Run proxy tests**; expected PASS.
- [ ] **Step 5: Write RED CRL tests** generating a CA, client certificate and signed CRL; revoked serial must be denied and invalid CRL signature rejected.
- [ ] **Step 6: Run CRL tests**; expected FAIL.
- [ ] **Step 7: Implement CRL loader/checker** with atomic last-good state and readiness degradation on reload error.
- [ ] **Step 8: Implement `main.go` TLS server** with `tls.RequireAndVerifyClientCert`, minimum TLS 1.2, configured server cert/key and client CA bundle.
- [ ] **Step 9: Add non-root Dockerfile** and README env contract.
- [ ] **Step 10: Run** `go test ./...`, `go vet ./...`, `go build ./cmd/device-edge`; expected PASS.
- [ ] **Step 11: Commit** `feat: add mTLS device edge proxy`.

### Task 3: Windows agent enrollment and secure state

**Files:**
- Create: `agents/windows-agent/go.mod`
- Create: `agents/windows-agent/internal/config/config.go`
- Create: `agents/windows-agent/internal/enroll/enroll_test.go`
- Create: `agents/windows-agent/internal/enroll/enroll.go`
- Create: `agents/windows-agent/internal/keystore/keystore.go`
- Create: `agents/windows-agent/internal/keystore/keystore_windows.go`
- Create: `agents/windows-agent/internal/keystore/keystore_nonwindows.go`
- Create: `agents/windows-agent/internal/state/state_test.go`
- Create: `agents/windows-agent/internal/state/state.go`

**Interfaces:**
- Produces: `enroll.CreateCSR(hostname)`, `enroll.ValidateEnrollmentResponse`, `state.Load/Save`, `keystore.Protect/Unprotect`.

- [ ] **Step 1: Write RED enrollment tests** proving generated CSR is P-256, response certificate matches private key, SPIFFE IDs equal response IDs and mismatches fail.
- [ ] **Step 2: Run** `go test ./internal/enroll`; expected FAIL.
- [ ] **Step 3: Implement CSR/response validation** using standard crypto/x509.
- [ ] **Step 4: Run enrollment tests**; expected PASS.
- [ ] **Step 5: Write RED atomic-state tests** proving config/state survives interrupted temp write and token is not persisted.
- [ ] **Step 6: Implement atomic JSON state store** with restrictive permissions where supported.
- [ ] **Step 7: Implement Windows DPAPI LocalMachine keystore** and non-Windows test shim guarded by build tags; production Windows path must never store PEM private key plaintext.
- [ ] **Step 8: Cross-compile** `GOOS=windows GOARCH=amd64 go test -c ./internal/keystore` and run Linux package tests.
- [ ] **Step 9: Commit** `feat: add Windows enrollment and secure identity store`.

### Task 4: Agent mTLS client, heartbeat and telemetry collectors

**Files:**
- Create: `agents/windows-agent/internal/client/client_test.go`
- Create: `agents/windows-agent/internal/client/client.go`
- Create: `agents/windows-agent/internal/heartbeat/heartbeat_test.go`
- Create: `agents/windows-agent/internal/heartbeat/heartbeat.go`
- Create: `agents/windows-agent/internal/telemetry/schema_test.go`
- Create: `agents/windows-agent/internal/telemetry/schema.go`
- Create: `agents/windows-agent/internal/telemetry/collect_windows.go`
- Create: `agents/windows-agent/internal/telemetry/collect_nonwindows.go`

**Interfaces:**
- Produces: authenticated `Client` methods `Heartbeat`, `AcquireCommands`, `MarkRunning`, `SubmitResult`, `SendTelemetry`.
- Produces telemetry samples matching the v0.6 allowlist exactly.

- [ ] **Step 1: Write RED client tests** using TLS test server proving client cert is presented and no Guardian identity headers are sent by agent.
- [ ] **Step 2: Implement mTLS client** with configurable CA pool and no insecure mode.
- [ ] **Step 3: Write RED heartbeat payload tests** for required capabilities, persisted session ID and timestamp.
- [ ] **Step 4: Implement heartbeat builder** and interval clamping.
- [ ] **Step 5: Write RED telemetry schema tests** for CPU/memory/disk labels/value constraints mirroring server v0.6.
- [ ] **Step 6: Implement collectors**; Windows implementation uses native APIs/counters, non-Windows implementation exists only for deterministic unit tests.
- [ ] **Step 7: Run** `go test ./...` and Windows cross-compile; expected PASS.
- [ ] **Step 8: Commit** `feat: add agent heartbeat and telemetry`.

### Task 5: Command executor without arbitrary shell

**Files:**
- Create: `agents/windows-agent/internal/commands/commands_test.go`
- Create: `agents/windows-agent/internal/commands/commands.go`
- Create: `agents/windows-agent/internal/commands/executor_windows.go`
- Create: `agents/windows-agent/internal/commands/executor_nonwindows.go`

**Interfaces:**
- Produces: `commands.Validate(RemoteCommand) error` and `Executor.Execute(ctx, RemoteCommand) Result`.

- [ ] **Step 1: Write RED validation tests** for exact schemas: empty args inventory, reboot delay 0..3600, service name regex; unsupported type and extra keys fail.
- [ ] **Step 2: Implement validator** without shell strings.
- [ ] **Step 3: Write RED executor tests** through an OS abstraction so CI verifies inventory trigger, reboot API invocation and SCM restart sequence without rebooting runner.
- [ ] **Step 4: Implement Windows executor** using native reboot API and SCM through `golang.org/x/sys/windows/svc/mgr`; no `os/exec` is allowed in command package.
- [ ] **Step 5: Add source test** rejecting `os/exec`, `cmd.exe`, `powershell` imports/strings in command executor.
- [ ] **Step 6: Run unit tests + Windows cross-compile**; expected PASS.
- [ ] **Step 7: Commit** `feat: execute typed Windows commands safely`.

### Task 6: Offline spool, retry and command loop

**Files:**
- Create: `agents/windows-agent/internal/spool/spool_test.go`
- Create: `agents/windows-agent/internal/spool/spool.go`
- Create: `agents/windows-agent/internal/backoff/backoff_test.go`
- Create: `agents/windows-agent/internal/backoff/backoff.go`
- Create: `agents/windows-agent/internal/runner/runner_test.go`
- Create: `agents/windows-agent/internal/runner/runner.go`

**Interfaces:**
- Produces durable queue for telemetry/results and main polling loop.

- [ ] **Step 1: Write RED spool tests** for atomic enqueue, restart recovery, 64 MiB/10k bounds, command-result priority and stable IDs.
- [ ] **Step 2: Implement file-backed spool** with temp+sync+rename and deterministic ordering.
- [ ] **Step 3: Write RED backoff tests** for exponential base 1 s, jitter bounds, 5 min cap and reset on success.
- [ ] **Step 4: Implement backoff** with injectable RNG/clock.
- [ ] **Step 5: Write RED runner tests**: heartbeat/telemetry scheduled; acquired command becomes running then terminal; network failure spools terminal result; next successful cycle drains same payload idempotently.
- [ ] **Step 6: Implement runner** with context cancellation and no unbounded goroutines.
- [ ] **Step 7: Run `go test -race ./...` on Linux-testable packages** and Windows compile.
- [ ] **Step 8: Commit** `feat: add durable endpoint operation loop`.

### Task 7: Signed updater and rollback state machine

**Files:**
- Create: `agents/windows-agent/internal/update/manifest_test.go`
- Create: `agents/windows-agent/internal/update/manifest.go`
- Create: `agents/windows-agent/internal/update/rollback_test.go`
- Create: `agents/windows-agent/internal/update/rollback.go`

**Interfaces:**
- Produces Ed25519 manifest verification and rollback planner independent of installer transport.

- [ ] **Step 1: Write RED tests** for canonical manifest signature, wrong signature, SHA mismatch, oversized download and downgrade rejection.
- [ ] **Step 2: Implement verifier** using standard `crypto/ed25519` and streaming SHA-256.
- [ ] **Step 3: Write RED rollback tests** simulating staged binary, previous binary, health marker timeout and successful promotion.
- [ ] **Step 4: Implement rollback state machine** with atomic rename and explicit rollback marker; platform process/service actions remain behind interface.
- [ ] **Step 5: Run update tests**; expected PASS.
- [ ] **Step 6: Commit** `feat: add signed agent update rollback`.

### Task 8: Windows service entrypoint and packaging

**Files:**
- Create: `agents/windows-agent/cmd/itguardian-agent/main.go`
- Create: `agents/windows-agent/internal/service/service_windows.go`
- Create: `agents/windows-agent/internal/service/service_nonwindows.go`
- Create: `agents/windows-agent/packaging/windows/Product.wxs`
- Create: `agents/windows-agent/README.md`
- Create: `.github/workflows/windows-agent-ci.yml`

**Interfaces:**
- Produces CLI `enroll`, `run`, `version` and SCM service mode.

- [ ] **Step 1: Write CLI/service behavior tests** for subcommand parsing and foreground cancellation.
- [ ] **Step 2: Implement entrypoint** and Windows SCM handler running under installed LocalService account.
- [ ] **Step 3: Add WiX definition** installing executable, ProgramData directory and auto-delayed service without embedded token.
- [ ] **Step 4: Add CI** using Windows runner: Go tests, amd64 build, arm64 compile, WiX MSI, SHA256SUMS artifact; Linux job builds/tests Device Edge and Docker image.
- [ ] **Step 5: Add source/secret checks**: no `InsecureSkipVerify: true`, no CA private key patterns, no `os/exec` in command package.
- [ ] **Step 6: Commit** `build: package Windows agent and device edge`.

### Task 9: Compose and clean-stack v0.7 E2E

**Files:**
- Modify: `compose.yaml`
- Modify: `compose.override.yaml`
- Modify: `.env.example`
- Create: `tests/v07-device-edge-e2e/README.md`
- Create: `tests/v07-device-edge-e2e/test_v07.py`
- Modify: `.github/workflows/windows-agent-ci.yml`

**Interfaces:**
- Adds Device Edge to server stack and full v0.7 integration gate.

- [ ] **Step 1: Write E2E assertions first**: generate enrollment token, create CSR/key, enroll via Gateway, start mTLS client, spoof Guardian headers, verify edge uses cert identity, heartbeat ONLINE, telemetry latest, command lifecycle and revocation denial.
- [ ] **Step 2: Add Device Edge Compose service** bound to `8443`, public trust mounts read-only, upstreams internal only, proxy shared secret server-side only.
- [ ] **Step 3: Extend CI clean-stack** to generate test server TLS cert and use PKI device CA/CRL without exposing CA private keys to edge.
- [ ] **Step 4: Run workflow on branch** and inspect all jobs; fix only evidenced failures.
- [ ] **Step 5: Commit** `test: certify v0.7 mTLS endpoint flow`.

### Task 10: Release promotion after same-SHA certification

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `MASTER.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`

**Interfaces:**
- Promotes v0.7.0 only after all prior tasks and CI are green.

- [ ] **Step 1: Confirm same candidate SHA** has Windows Agent CI + every existing v0.1–v0.6 workflow success.
- [ ] **Step 2: Confirm clean-stack from empty volumes** and artifact hashes/MSI are attached to the candidate workflow.
- [ ] **Step 3: Update stale roadmap state**: v0.6 DONE/main; v0.7 DONE/main candidate; v0.8 active gate.
- [ ] **Step 4: Set `VERSION` to `0.7.0`**, update docs/checklists and changelog with exact certified capabilities; do not claim Windows 7/8 support.
- [ ] **Step 5: Run final CI on promotion SHA** and require all gates green again.
- [ ] **Step 6: Mark PR ready and squash-merge only with expected head SHA**.
- [ ] **Step 7: Verify `main` VERSION and README after merge; then activate v0.8 Web Console branch separately.
