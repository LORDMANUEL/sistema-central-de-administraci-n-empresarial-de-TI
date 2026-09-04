# IT Guardian v0.8.0 Web Console MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a secure, installable Web Console that operates the certified v0.7 core end-to-end through Gateway.

**Architecture:** Complete the missing administrative northbound device/command/telemetry contracts, then place a FastAPI BFF between the browser and Gateway so Guardian JWTs remain server-side. A React/TypeScript/Vite SPA consumes only explicit `/console/api/*` BFF endpoints.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy, React + TypeScript + Vite, React Router, TanStack Query, Vitest/Testing Library, Docker Compose, Playwright E2E.

**Spec:** `docs/superpowers/specs/2026-08-28-web-console-v08-design.md`

## Global Constraints
- `VERSION` remains `0.7.0` until same-SHA v0.8 certification.
- Browser must never receive/store Guardian access or refresh tokens.
- BFF calls Gateway only; no direct microservice browser/BFF bypass.
- Gateway never exposes `/api/v1/device/*`.
- Command allowlist remains `inventory.refresh`, `device.reboot`, `service.restart`; no shell.
- Existing v0.1-v0.7 CI must remain green.

---

### Task 1: Agent Control administrative device API
**Files:** modify `services/agent-control-service/app/api.py`, `auth.py`, schemas/models helpers as required; add `services/agent-control-service/tests/test_admin_devices.py`.
**Produces:** Identity-authenticated `GET /api/v1/devices` and `GET /api/v1/devices/{device_id}` with tenant isolation.
- [ ] Write failing tests for list/get authorization, filters and 404/403 behavior.
- [ ] Run targeted pytest and confirm RED because routes are absent.
- [ ] Implement minimal admin read API reusing authoritative core validation.
- [ ] Run targeted + full Agent Control tests GREEN.
- [ ] Commit.

### Task 2: Gateway admin routes for v0.6 operations
**Files:** modify `services/gateway-service/app/config.py`, `routes.py`, tests and Compose/env wiring.
**Produces:** seven explicit northbound admin routes for devices/commands/telemetry; `/device/*` still denied.
- [ ] Add failing registry/proxy tests for exact route set, auth mode and forbidden device-plane paths.
- [ ] Run tests RED.
- [ ] Add three upstream settings and explicit policies only.
- [ ] Run Gateway tests + compose config GREEN.
- [ ] Commit.

### Task 3: Web Console BFF secure session
**Files:** create `services/web-console-service/pyproject.toml`, `app/config.py`, `app/session.py`, `app/gateway.py`, `app/api/session.py`, `app/main.py`, tests.
**Produces:** opaque HttpOnly browser session; server-side Guardian token pair; login/me/logout and one-refresh retry.
- [ ] Write failing tests asserting tokens never appear in cookies/body and logout/expiry/refresh behavior.
- [ ] Run tests RED.
- [ ] Implement bounded in-memory session store, cookie policy and Gateway client.
- [ ] Run tests GREEN + compile.
- [ ] Commit.

### Task 4: Explicit BFF resource routes
**Files:** create feature routers under `services/web-console-service/app/api/`.
**Produces:** no catch-all; typed pass-through handlers for users, tenants, assets, devices, commands, enrollment, telemetry and audit.
- [ ] Write failing allowlist tests including rejection of `/api/v1/device/*`.
- [ ] Run RED.
- [ ] Implement explicit handlers preserving method/query/body and authorization server-side.
- [ ] Run GREEN.
- [ ] Commit.

### Task 5: React application shell + authenticated routing
**Files:** create `apps/web-console/package.json`, Vite/TS config, `src/main.tsx`, `src/App.tsx`, `src/api/client.ts`, session feature, layout/nav styles/tests.
**Produces:** login, session bootstrap, protected shell and navigation.
- [ ] Write Vitest tests for unauthenticated redirect, login success/failure and logout.
- [ ] Run RED.
- [ ] Implement minimal shell and session query/mutations.
- [ ] Run GREEN + `npm run build`.
- [ ] Commit.

### Task 6: Devices + Overview
**Files:** feature components/hooks/tests under `apps/web-console/src/features/devices` and `overview`.
**Produces:** real device table, filters, detail with CPU/RAM/disk telemetry and overview counts.
- [ ] Write tests for ONLINE/OFFLINE rendering, telemetry formatting, empty/error states.
- [ ] Run RED.
- [ ] Implement table-first UI using BFF endpoints only.
- [ ] Run GREEN + build.
- [ ] Commit.

### Task 7: Commands + Enrollment
**Files:** command/enrollment features and tests.
**Produces:** command list/create/cancel with three typed commands; token create/list/revoke with non-persistent raw token display.
- [ ] Write failing behavior tests including invalid reboot/service inputs and raw-token persistence guard.
- [ ] Run RED.
- [ ] Implement minimal typed forms/tables.
- [ ] Run GREEN + build.
- [ ] Commit.

### Task 8: Assets + Organization + Audit
**Files:** assets/organization/audit features and tests.
**Produces:** remaining MVP admin views over existing Gateway contracts.
- [ ] Write tests for list/detail/loading/error and audit verification state.
- [ ] Run RED.
- [ ] Implement pages.
- [ ] Run GREEN + build.
- [ ] Commit.

### Task 9: Docker/Compose + v0.8 CI
**Files:** BFF Dockerfile/.dockerignore, frontend build integration, `compose.yaml`, `compose.override.yaml`, `.env.example`, `.github/workflows/web-console-ci.yml`.
**Produces:** non-root loopback-published Web Console and reproducible CI.
- [ ] Add failing config/security checks before runtime wiring.
- [ ] Add Docker multi-stage build and Compose service.
- [ ] Validate effective Compose, non-root image, backend/frontend tests.
- [ ] Commit.

### Task 10: Clean-stack E2E and promotion
**Files:** E2E script/tests, documentation/version files only after certification.
**Produces:** browser-accessible MVP certified with real v0.7 endpoint flow.
- [ ] Start from empty volumes.
- [ ] Certify login → device → telemetry → typed command → result → Audit.
- [ ] Repeat existing v0.1-v0.7 workflows on candidate SHA.
- [ ] Update README/ROADMAP/MASTER/CHANGELOG and set `VERSION=0.8.0` only after all gates pass.
- [ ] Open/ready PR, verify same SHA, merge to `main` only when green.
