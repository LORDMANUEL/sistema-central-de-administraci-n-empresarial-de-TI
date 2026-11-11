# IT Guardian — control baseline SOC 2 / ISO/IEC 27001 (P0)

**Status:** technical alignment work in progress; not an assertion of certification, SOC 2 report or audit opinion.

**Standards reference:** ISO/IEC 27001:2022 and Amd 1:2024 (ISMS management requirements); ISO/IEC 27002:2022 guidance; AICPA SOC 2 Trust Services Criteria (Security common criteria and optional categories). An external auditor defines scope and examines operation of controls; technology alone cannot establish compliance.

## Scope

In-scope: GitHub code and release workflows, self-hosted Docker infrastructure, IT Guardian administrative plane, endpoint device plane, enrollment PKI and incident response. Out-of-scope until documented: corporate HR/vendor governance, facilities, third-party processors and customer-owned host security.

## Traceability matrix

| Risk/control | Technical implementation currently documented | Evidence needed / open P0 control | ISO 27001:2022 Annex A related themes | SOC 2 category |
| --- | --- | --- | --- | --- |
| Identity and least privilege | Argon2, JWT Ed25519/JWKS, RBAC, tenant-scoping | access-review records, privilege tests, joiner/mover/leaver procedure | A.5.15–5.18, A.8.2–8.5 | Security / CC6 |
| Device identity | one-use enrollment, X.509 mTLS, CRL, DPAPI local | proof of certificate revocation, key rotation, compromised device response | A.8.5, A.8.20–8.24 | Security / CC6 |
| Separation / transport | Device Edge separate from admin BFF, tokens server-side | firewall exposure report, TLS renewal, reverse proxy test | A.8.20–8.24 | Security / CC6 |
| Logs / forensics | append-only tamper-evident audit chain | retention, clock sync, export to immutable storage, alert rehearsal | A.8.15–8.17 | CC7 |
| Change management | pull request + CI, build and E2E workflows | branch protection, approvals, reproducible artifact provenance and SBOM | A.8.25–8.32 | CC8 |
| Availability | health endpoints, offline spool/retry | RTO/RPO policy, backup verification, periodic restore rehearsal, recovery runbooks | A.5.29–5.30, A.8.13–8.14 | Availability |
| Secrets | opaque web sessions; separate signers and endpoint private keys | secret rotation procedure, environment audit, secret scanning, secure provisioning | A.8.12, A.8.24 | CC6 |
| Vulnerability management | limited core baseline | dependabot/SCA, SAST, OS patching, vulnerability SLAs, pentest | A.8.8 | CC7 |
| Data governance | per-domain stores and tenant isolation | classification, minimization, retention/deletion policy, DPIA when relevant | A.5.12–5.14, A.5.34 | Confidentiality / Privacy |
| Supplier and host | self-hosted model, nonroot services documented | vendor inventory, risk assessment, host baseline CIS, privileged Docker review | A.5.19–5.23, A.8.9 | CC3 / CC9 |

Mappings are conceptual pointers, NOT a complete statement of applicability nor copies of the licensed standards.

## P0 blocking technical requirements

1. No plaintext or placeholder secrets in production, environment files root-only with chmod 600; never commit private material.
2. Expose only HTTPS web console via reverse proxy and mTLS Device Edge to intended networks. Block databases, Valkey, NATS and internal admin ports externally; verify active host firewall.
3. Enable MFA or documented compensating controls for privileged administrators before production; administrative role access must be reviewed.
4. Keep endpoint key private; verify enrollment replay denial, CRL, expiry, revocation and certificate pinning semantics.
5. Run containers as non-root, read-only filesystems where supported, drop Linux capabilities and set resource ceilings on each service after compatibility testing.
6. Produce SBOM and lock dependency versions; scan dependencies and images and record findings/remediation.
7. Run explicit PostgreSQL backup and restore tests, signed-off RPO/RTO; do not confuse config archive with a data backup.
8. Verify logs cannot be erased by endpoint admins; ship to restricted/immutable retention and synchronize clocks.
9. Create a documented change approval, incident response playbook, access review cadence and risk register.
10. Perform third-party penetration test and external assurance readiness review prior to any certification claim.

## Evidence package for each release

Store CI commit SHA, clean-stack logs, Windows MSI install/uninstall logs, Debian .deb SHA256, docker compose config report (secrets REDACTED), results of role/tenant isolation, mTLS revocation evidence, dependency scan, disaster recovery rehearsal, reviews and sign-off. Never publish live credentials or identifying endpoint data as CI artifacts.

## Operational boundary

The P0 Debian tool does not change global firewall, SSH, packages, Docker daemon config or existing host services. The operator is responsible for hardening Debian host and TLS reverse proxy through a reviewed runbook. Running Docker commands as root is privileged, and access to the Docker socket is equivalent to host-level privilege.

## Governance artifacts still required for actual external assurance

ISMS scope and context, leadership and policies, asset/risk register, treatment plan and Statement of Applicability, objectives and performance measures, internal audit, management review, corrective actions and ongoing operation evidence. SOC 2 additionally needs system description, management assertions, defined Trust Services Criteria scope and independent practitioner examination. SOC 2 Type II requires evidence over an observation period.
