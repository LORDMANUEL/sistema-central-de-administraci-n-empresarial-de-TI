# Changelog

All notable IT Guardian changes are documented here.

## [0.7.0] - 2026-08-28

### Device Edge
- Added a dedicated Go mTLS endpoint edge on port 8443.
- Device identity is derived from the verified X.509 SPIFFE URI SAN; caller-controlled Guardian/forwarding headers are stripped.
- Only the five v0.6 device-plane POST routes are allowlisted.
- Added signed-CRL validation, last-good retention and fail-closed behavior after CRL expiry.
- Added idempotent TLS server bootstrap with a separate CA volume; the serving runtime mounts public/runtime material only and runs non-root.

### Windows Agent Modern
- Added Go Windows agent with ECDSA P-256 CSR enrollment and strict certificate chain/SPIFFE/serial/fingerprint validation.
- Device private key is protected with Windows DPAPI LocalMachine; enrollment tokens are never persisted.
- Added mTLS device client, heartbeat/capability negotiation and native Windows CPU/RAM/disk telemetry.
- Added typed command execution for `inventory.refresh`, `device.reboot` and `service.restart` using native WinAPI/SCM; no arbitrary shell is exposed.
- Added bounded crash-safe offline spool (64 MiB / 10,000 items), priority for terminal command results and exponential retry/backoff.
- A failed terminal-result upload is retried from the same durable payload without reexecuting the command.

### Signed updates
- Added Ed25519-signed canonical update manifests, HTTPS-only catalog/payload transport, bounded download and streaming SHA-256 verification.
- Added anti-downgrade checks, atomic staging, fixed helper transaction paths and health-marker commit/rollback.
- Update catalog URL and Ed25519 public key are pinned in `agent.json`; the CLI cannot substitute arbitrary update sources.
- The helper controls only `ITGuardianAgent`, waits for the parent process, promotes staged content and restores the previous binary if health does not arrive.

### Windows packaging
- Added x64 WiX v4 MSI and x64/arm64 EXE builds.
- Service installs as `NT AUTHORITY\LocalService`, Auto + delayed-auto, and remains stopped before enrollment.
- MSI installs a valid non-secret `agent.example.json` under ProgramData.
- CI performs silent MSI install/uninstall, verifies service account/start policy/command line and confirms cleanup.
- Added SHA-256 artifact manifest.

### Certification
- Agent portable `go test -race` + `go vet`: success.
- Windows Go tests/vet and x64 execution: success; arm64 compile gate: success.
- Device Edge race/vet/build/non-root image: success.
- v0.7 clean-stack from empty volumes: success.
- Real Enrollment-issued certificate and HTTPS mTLS Device Edge flow: success.
- Header spoofing, heartbeat/ONLINE, telemetry/latest, command lifecycle, result replay and CRL revocation: success.
- Device Edge TLS CA private key isolation: success.
- v0.6 regression certification completed two clean-stack cycles with the v0.7 stack changes.

## [0.6.0] - 2026-08-27

### Endpoint Operations Core
- Added Agent Control heartbeat/capabilities/online-offline state and outbox events.
- Added typed Command Service with idempotency, leases, acquire/running/result/cancel and replay protection.
- Added bounded Telemetry Service with allowlisted metrics, batch dedupe and latest reads.
- Added normalized trusted device principal boundary and protected Gateway admin/device-plane separation.
- Added v0.6 clean-stack certification including NATS outage recovery, Audit and secret isolation.

## [0.5.0] - 2026-08-26

### Gateway + Audit
- Added static northbound Gateway allowlist, JWT/JWKS validation, header sanitization, request limits and rate limiting.
- Administrative mutations are audit-intent fail-closed.
- Added independent Audit database, durable JetStream ingestion, dedupe, append-only records and verifiable hash chain.

## [0.4.0] - 2026-08-24

### Core release
- Certified PKI + Enrollment as the v0.4 end-to-end capability.
- Added independent `guardian_pki` and `guardian_enrollment` databases with Alembic round-trips.
- Added full Compose deployment for Enrollment DB init, migration, API on port 8005 and outbox worker.
- Added a clean-stack E2E from Identity bootstrap through Tenant/Asset, one-time Enrollment token, endpoint CSR, PKI issuance, X.509 verification and JetStream `device.enrolled`.

### Enrollment
- One-time high-entropy tokens are bound to tenant + asset and persisted only as SHA-256 hash plus a non-secret hint.
- Atomic reservation creates stable `device_id` + `issuance_id` before the PKI network call.
- Identical retries reuse the same enrollment/certificate; mismatched token reuse is rejected as replay.
- CSR validation accepts RSA >=2048 and EC P-256/P-384 while endpoint private keys remain local.
- Added a dedicated Enrollment Ed25519 signer and public JWKS for short-lived PKI grants.
- Added safe PKI retry/recovery semantics and administrative enrollment inventory.
- Added transactional outbox events and secret-safe observability.

### PKI
- Guardian Root CA RSA-4096 + Device Intermediate RSA-3072 with fail-safe idempotent initialization.
- Root private key is available only to `pki-ca-init`; runtime API mounts only Intermediate material read-only.
- Added idempotent device certificate issuance, persistent revocation, signed CRL and atomic certificate rotation.
- Added Enrollment Ed25519 grant verification bound to tenant, asset, device, issuance ID and CSR SHA-256.

## [0.3.0-rc.1] - 2026-08-24

### Added
- Tenant-scoped Asset authorization through Tenant Service without cross-service database access.
- `platform_admin` global access, `org_admin` tenant write access and read-only access for other active tenant memberships.
- Tenant suspension enforcement in Asset Service.
- Inter-service validation of `site_id` and `department_id` before asset persistence.
- Clean-stack E2E gate covering `Identity -> Tenant -> Site/Department -> Asset`.
- JetStream E2E assertion for `guardian.asset.created`.
- Versioned event envelope shared with Tenant (`schema_version`, `type`, `data`).

## [0.3.0-dev.1] - 2026-08-23

### Added
- Product roadmap focused on end-to-end functional gates.
- Asset Service canonical domain foundation.
- Stable `guardian_asset_id`, tenant/site/department references and asset classification.
- External identity correlation and transactional outbox events.
- Identity Ed25519/JWKS token verification, health/readiness, metrics and request IDs.
- Asset migration, non-root Docker and CI gates.

## [0.2.0-dev.1] - 2026-08-21

### Added
- Tenant Service with tenants, memberships, sites and hierarchical departments.
- Tenant-scoped authorization backed by Identity Ed25519 JWKS.
- Transactional outbox with NATS JetStream worker and independent database migration.

## [0.1.0-dev.2] - 2026-08-21

### Security
- Replaced shared-secret HS256 signing with Ed25519/EdDSA asymmetric JWT signing.
- Added `kid`, issuer and audience claims and public JWKS.

## [0.1.0-dev.1] - 2026-08-21

### Added
- Microservice-first master architecture and Enterprise Stable roadmap.
- Identity Service with one-time platform bootstrap, Argon2, access/refresh tokens, RBAC, health/metrics and non-root Docker.
