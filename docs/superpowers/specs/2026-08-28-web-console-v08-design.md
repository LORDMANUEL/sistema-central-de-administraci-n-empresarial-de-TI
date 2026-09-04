# IT Guardian v0.8.0 Web Console MVP — Design

## Goal
Deliver the first production-facing administrative UI for the already certified v0.7 core. The browser must manage users/tenants/assets/enrollment, see real device state and telemetry, create/cancel allowlisted commands, and inspect Audit through one northbound surface.

## Scope
v0.8.0 contains three tightly coupled pieces only:

1. minimal administrative API completion for Agent Control + Gateway exposure of the v0.6 admin contracts;
2. `web-console-service`, a small FastAPI BFF that owns the browser session and serves the compiled SPA;
3. `apps/web-console`, a React + TypeScript + Vite console.

Software/Patch/Policy remains v0.9. Tickets, remote support, security, mobile and legacy endpoint work remain outside v0.8.

## Security model
- Browser never receives or stores Guardian access/refresh tokens in `localStorage`, `sessionStorage`, IndexedDB or readable cookies.
- BFF stores access/refresh tokens server-side in an in-memory bounded session store for v0.8; browser receives only a random opaque session cookie marked `HttpOnly`, `SameSite=Strict`, `Secure` when TLS is enabled.
- Session cookie is rotated at login, deleted at logout and expires after inactivity.
- BFF calls only a static allowlist of Gateway paths; it has no catch-all proxy.
- BFF never calls service containers directly. All administrative traffic goes to Gateway.
- Device Edge remains exclusively for `/api/v1/device/*`; Web Console must never send Device Edge trusted headers.
- Gateway keeps its existing JWT validation and downstream services keep their own authorization.
- Mutations continue to use Gateway audit-intent fail-closed behavior.
- No arbitrary remote shell is added. Command types remain exactly `inventory.refresh`, `device.reboot`, `service.restart`.

## Administrative API completion
### Agent Control
Add Identity-authenticated northbound endpoints:
- `GET /api/v1/devices?tenant_id=&state=&limit=`
- `GET /api/v1/devices/{device_id}`

Responses expose only administrative state: device/tenant/asset IDs, state, agent version, platform/platform version when known, capabilities, last seen and session timestamps. Tenant authorization is resolved through the same authoritative core validation path used elsewhere; no trusted proxy token is accepted on these admin endpoints.

### Gateway
Add fixed upstream URLs for Agent Control, Command and Telemetry and register only these administrative routes:
- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `POST /api/v1/commands`
- `GET /api/v1/commands`
- `GET /api/v1/commands/{command_id}`
- `POST /api/v1/commands/{command_id}/cancel`
- `GET /api/v1/telemetry/devices/{device_id}/latest`

`/api/v1/device/*` remains absent from northbound Gateway routes.

## BFF surface
Public browser-facing BFF API:
- `POST /console/api/session/login`
- `POST /console/api/session/logout`
- `GET /console/api/session/me`
- explicit read/write route handlers for the exact UI resources above plus current Identity/Tenant/Asset/Enrollment/Audit northbound routes.

The BFF automatically refreshes an expired access token once using the server-side refresh token. Failed refresh destroys the session and returns 401.

## Web Console information architecture
Primary navigation:
- Overview
- Devices
- Assets
- Commands
- Enrollment
- Organization
- Audit
- Users (platform admins only when API authorization permits)

### Login
Email + password, no token visibility. After login load `/users/me` and tenants.

### Overview
Operational counts computed from real API responses: assets, enrolled devices, online/offline devices, recent commands and audit verification state. No invented metrics.

### Devices
Table-first interface with search/filter by tenant/state. Columns: hostname/asset identity when resolvable, device ID, state, agent version, last seen. Selecting a row opens device detail.

### Device detail
- identity/state/last seen;
- latest CPU/RAM/disk telemetry from the real telemetry endpoint;
- recent commands for the device;
- command actions limited to inventory refresh, delayed reboot and service restart.

### Assets
Canonical asset list and detail using Asset Service. Enrollment/device relation displayed where available.

### Commands
Global command table with state filter and terminal result state. Create/cancel only through real Command Service contracts.

### Enrollment
Create/list/revoke one-time enrollment tokens and list enrolled devices. Raw token is shown only in the immediate create response if the backend returns it; the UI never persists it.

### Organization
Tenant, site, department and membership views using existing Gateway routes.

### Audit
Read-only records and chain verification status.

## Frontend architecture
React 18+, TypeScript strict, Vite, React Router, TanStack Query for server state, native fetch wrapper for BFF calls, CSS modules/global design tokens. Keep components small and feature-scoped. No frontend global token store.

Design direction: enterprise command-center, light neutral canvas, dark navy navigation rail, blue accent, restrained semantic green/amber/red state indicators, table-led density, minimal decorative chrome. Accessibility requires keyboard navigation, visible focus, semantic tables/forms, reduced-motion support and WCAG AA contrast.

## Runtime and deployment
- `web-console-service` runs non-root in Docker and serves the built SPA under `/console/` plus `/console/api/*`.
- Compose publishes it to loopback only by default (proposed `127.0.0.1:${WEB_CONSOLE_PORT:-8088}`) pending external reverse proxy/TLS.
- BFF reaches Gateway over the internal Docker network.
- No BFF secret or session data is baked into the frontend bundle.

## Testing / Definition of Done
v0.8 is not complete until the same SHA passes:
1. Agent Control admin API unit/integration tests including tenant isolation;
2. Gateway route-registry/security tests proving the new admin routes exist and `/device/*` remains blocked;
3. BFF session tests proving JWTs never reach browser responses/cookies and refresh/logout behavior is correct;
4. frontend unit/component tests for login, device table, device detail telemetry, typed commands and error states;
5. TypeScript build/lint/test;
6. Docker non-root checks for BFF;
7. clean-stack E2E: login → tenant → device ONLINE from v0.7 agent flow → console lists device → telemetry visible → create allowlisted command → result visible → Audit chain verifies;
8. existing v0.1-v0.7 workflows remain green;
9. README/ROADMAP/MASTER/CHANGELOG updated;
10. only then set `VERSION=0.8.0` and merge to `main`.
