# Tenant Service Implementation Plan

**Goal:** Deliver a complete independently deployable tenant/organization boundary with JWT/JWKS authorization, sites, departments, memberships and reliable event outbox.

**Spec:** `docs/superpowers/specs/2026-08-21-tenant-service-design.md`

- [x] RED/GREEN: service configuration, database and health endpoints.
- [x] RED/GREEN: Identity JWKS access-token verification and stable auth errors.
- [x] RED/GREEN: tenant create/list/get/update with platform-admin boundary.
- [x] RED/GREEN: membership create/list/status and tenant-scoped access.
- [x] RED/GREEN: site create/list/update and per-tenant unique codes.
- [x] RED/GREEN: department hierarchy, create/list/update and parent/cycle validation.
- [x] RED/GREEN: transactional outbox rows and rollback behavior.
- [x] RED/GREEN: outbox worker marks published only after publisher ACK and avoids hot-loop retries.
- [x] Add NATS JetStream publisher with `Nats-Msg-Id=event_id` and at-least-once semantics.
- [x] Add Alembic migration and verify upgrade/downgrade/upgrade locally.
- [x] Add non-root Docker image and Compose services for API, migration worker, outbox worker and NATS.
- [x] Add metrics, request IDs, structured logs, docs and CI.
- [x] Run full local test suite with `python -m pytest -q`: **25 passed**.
- [x] Run `compileall`: **OK**.
- [x] Parse TOML/YAML configuration: **OK**.
- [ ] Confirm GitHub Actions Python 3.12, Docker build and Compose validation are visible and green.
- [x] Open stacked draft PR #2 against `feature/v0.1.0-foundation` after pushing the verified branch.

## Verification notes

- Local runtime: Python 3.13; CI target: Python 3.12. The console `pytest` launcher in this harness omits the project directory from `sys.path`; `python -m pytest` is used explicitly in docs/CI and passes all tests.
- Local Docker CLI is unavailable; image build and `docker compose config --quiet` are encoded in CI.
- Tenant DB is independently named `guardian_tenant`; Identity remains `guardian_identity`.
- NATS monitor and backend HTTP ports bind to `127.0.0.1` by default until Gateway Service is introduced.
- Stacked review: PR #2 (`feature/v0.2.0-tenant` -> `feature/v0.1.0-foundation`).
