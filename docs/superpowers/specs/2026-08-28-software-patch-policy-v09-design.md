# IT Guardian v0.9.0 — Software + Patch + Policy Design

## Objective

Add a production-grade endpoint software/patch/policy layer on top of the certified v0.8 core without reopening closed service boundaries. v0.9 must let an administrator see installed software, see Windows update posture, define versioned desired-state policies, target those policies to tenant/site/department/asset/device scopes, and execute only explicitly approved software/patch actions through the existing secure device plane.

## Non-negotiable constraints

- `VERSION` remains `0.8.0` until the same v0.9 candidate SHA passes all v0.1-v0.9 gates.
- No arbitrary shell, PowerShell, `cmd.exe`, script upload, or free-form process execution.
- Device identity still comes only from Device Edge mTLS/SPIFFE normalization.
- Browser still talks only to Web Console BFF; BFF talks only to Gateway.
- Every new backend is an independent service/database/migration/outbox boundary.
- Every mutating administrative operation is identity-authenticated and auditable.
- Every device operation is allowlisted, size-bounded, replay/idempotency aware, and tenant/asset/device bound.
- Existing Windows 10/11 modern target remains unchanged.
- No v0.10 Tickets/Help Client work enters this release.

## Platform primitives

### Windows software inventory

The Windows agent reads installed-product metadata from the standard uninstall registry locations rather than invoking package-manager shells. Microsoft documents Windows Installer product metadata under `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall`; the collector additionally inspects the 32-bit WOW6432Node uninstall view and the current-machine registry view used by non-MSI applications. Each entry is normalized before upload and entries without a display name are ignored.

Normalized fields:

- `software_id`: deterministic SHA-256 identity derived from normalized publisher + name + architecture + product code when available.
- `name`.
- `version`.
- `publisher`.
- `architecture`: `x64`, `x86`, `arm64`, or `unknown`.
- `product_code`: optional MSI product GUID.
- `install_date`: optional date.
- `install_location`: optional, max 1024 bytes.
- `uninstall_kind`: `msi`, `registry`, or `unknown`; informational only in v0.9.

The agent never uploads uninstall command strings.

### Windows patch inventory/execution

Use Windows Update Agent (WUA) COM APIs directly. `IUpdateSession` provides update searcher/downloader/installer objects; `IUpdateSearcher::Search` performs update discovery, and installation uses the WUA installer interfaces. No PowerShell or external package-manager process is used.

The v0.9 agent exposes an internal `PatchProvider` interface so COM code is isolated behind a testable boundary.

Patch records normalize:

- stable Windows Update identity/revision;
- KB article IDs;
- title;
- categories;
- severity when WUA exposes it;
- downloaded/installed/hidden state;
- reboot required;
- EULA accepted state;
- observed timestamp.

The agent may search and install only through typed commands produced by Patch Service. It never accepts arbitrary WUA search criteria from the server.

## Service boundaries

### 1. Software Inventory Service

Directory: `services/software-service`.

Responsibilities:

- receive complete software snapshots from a normalized device principal;
- bound snapshots to tenant/asset/device identity;
- deduplicate by `snapshot_id`;
- store canonical current software plus snapshot history;
- compute added/removed/version-changed diffs transactionally;
- expose tenant-scoped admin reads;
- emit `software.snapshot.received`, `software.added`, `software.removed`, and `software.version_changed` through an outbox.

Device API:

- `POST /api/v1/device/software/snapshots`

Admin API:

- `GET /api/v1/software/devices/{device_id}`
- `GET /api/v1/software/devices/{device_id}/history`
- `GET /api/v1/software/catalog`

Limits:

- maximum 5000 entries/snapshot;
- maximum encoded body 2 MiB;
- name/publisher/version lengths bounded;
- a duplicate snapshot returns the existing snapshot result without rewriting history.

### 2. Patch Service

Directory: `services/patch-service`.

Responsibilities:

- receive WUA scan reports;
- store per-device patch posture/history;
- expose missing/installed/reboot-required state;
- create typed patch deployment jobs;
- fan deployment jobs into existing Command Service using a fixed command contract;
- track command IDs and reconcile terminal results;
- emit `patch.scan.received`, `patch.deployment.created`, `patch.deployment.succeeded`, `patch.deployment.failed`, and `patch.reboot_required`.

Device API:

- `POST /api/v1/device/patches/scans`

Admin API:

- `GET /api/v1/patches/devices/{device_id}`
- `GET /api/v1/patches/catalog`
- `POST /api/v1/patch-deployments`
- `GET /api/v1/patch-deployments`
- `GET /api/v1/patch-deployments/{deployment_id}`
- `POST /api/v1/patch-deployments/{deployment_id}/cancel`

Command contract added to Command Service:

- `software.inventory.refresh` — empty args.
- `patch.scan` — `{ "source": "managed" }` only.
- `patch.install` — `{ "update_ids": ["<stable-id>"], "allow_reboot": false }`; 1..100 exact IDs, max body 64 KiB.
- `policy.refresh` — empty args.

No command accepts a URL, executable path, shell fragment, installer arguments, WUA query criteria, or script text.

### 3. Policy Service

Directory: `services/policy-service`.

Responsibilities:

- version immutable policy revisions;
- manage active/inactive policy definitions;
- target policies to tenant, site, department, asset, or device selectors;
- resolve effective policy set deterministically for a device;
- issue an opaque policy-set version/ETag;
- accept compliance evaluations from devices;
- expose compliance summaries and per-device details;
- emit `policy.created`, `policy.revision.created`, `policy.assignment.changed`, `policy.compliance.changed`.

Supported v0.9 policy types:

1. `patch.ring`
   - `mode`: `notify`, `manual`, `automatic`.
   - `defer_days`: 0..30.
   - `allow_reboot`: boolean.
   - `maintenance_window`: optional UTC day/time window.
2. `software.require`
   - normalized `publisher`, `name`, optional minimum version.
   - compliance-only in v0.9; no generic installer execution.
3. `software.forbid`
   - normalized `publisher`, `name`, optional version predicate.
   - compliance-only in v0.9; no automatic arbitrary uninstall.

Device API:

- `GET /api/v1/device/policies/effective`
- `POST /api/v1/device/policies/compliance`

Admin API:

- `POST /api/v1/policies`
- `GET /api/v1/policies`
- `GET /api/v1/policies/{policy_id}`
- `POST /api/v1/policies/{policy_id}/revisions`
- `POST /api/v1/policies/{policy_id}/assignments`
- `DELETE /api/v1/policies/{policy_id}/assignments/{assignment_id}`
- `GET /api/v1/policy-compliance`
- `GET /api/v1/policy-compliance/devices/{device_id}`

Policy resolution precedence, highest first:

`device > asset > department > site > tenant`

Within the same specificity, the newest active revision wins only for the same policy key. Different policy keys compose. A conflict that cannot be deterministically composed is rejected at assignment time instead of silently choosing one.

## Device Edge

Device Edge adds only these explicit routes:

- `POST /api/v1/device/software/snapshots` -> Software Service.
- `POST /api/v1/device/patches/scans` -> Patch Service.
- `GET /api/v1/device/policies/effective` -> Policy Service.
- `POST /api/v1/device/policies/compliance` -> Policy Service.

The same certificate revocation, SPIFFE parsing, header stripping, CRL validity, request limits, and non-root runtime rules from v0.7 remain mandatory.

## Windows Agent

New packages under `agents/windows-agent/internal`:

- `software`: registry collector + deterministic normalization/snapshot.
- `patch`: WUA abstraction, Windows COM implementation, scan normalization, install executor.
- `policy`: effective-policy cache, evaluation engine, compliance payload.

Runner order becomes:

1. drain durable terminal-result spool;
2. heartbeat;
3. telemetry;
4. scheduled software snapshot if due or forced;
5. scheduled patch scan if due or forced;
6. policy refresh/compliance if ETag changed or due;
7. acquire and execute typed commands.

Default schedules:

- software snapshot: every 6 hours;
- patch scan: every 6 hours;
- policy refresh: every 15 minutes;
- existing heartbeat/telemetry behavior unchanged.

All new payloads use the existing offline spool. Terminal command results keep higher priority than inventory/scan/compliance records.

## Gateway and Web Console BFF

Gateway gets version-layered `v09_routes.py`; base and v0.6/v0.8 route files remain unchanged. Only administrative routes become northbound. Device routes stay inaccessible through Gateway.

Web Console BFF registers explicit Software, Patches, Patch Deployments, Policies and Compliance routes. No catch-all proxy is introduced.

## Web Console UI

New top-level navigation entries permitted by RBAC:

- Software.
- Parches.
- Políticas.

Software view:

- tenant/site scoped;
- device/software catalog table;
- version/publisher search;
- per-device installed list and snapshot timestamp;
- diff history.

Patches view:

- missing/installed/reboot-required filters;
- per-device posture;
- create deployment with selected update IDs and explicit target devices;
- explicit confirmation before deployment;
- deployment state linked to command lifecycle.

Policies view:

- policy list/status;
- immutable revision history;
- assignment scope form;
- compliance summary and device drill-down.

RBAC:

- `platform_admin`: full v0.9 access.
- `org_admin`: full tenant-scoped v0.9 access.
- `security_admin`: software/patch/policy read + policy/patch administration tenant-scoped.
- `it_operator`: software/patch read + patch deployment; policy read.
- `helpdesk`: software/patch read only.
- `auditor`: software/patch/policy/compliance read only.
- `viewer`: software/patch/compliance read only.

Backend remains authoritative; UI hiding is defense-in-depth and usability only.

## Data protection and audit

- software snapshots never include uninstall command strings, license keys, user profile paths, or executable contents;
- patch data never includes downloaded update binaries;
- policy bodies are validated typed JSON, not executable code;
- administrative mutations require Gateway audit intent;
- service outboxes feed immutable Audit records;
- device identifiers are never trusted from client headers.

## Idempotency and failure behavior

- software snapshots dedupe on `(device_id, snapshot_id)`;
- patch scans dedupe on `(device_id, scan_id)`;
- compliance reports dedupe on `(device_id, policy_set_version, evaluation_id)`;
- patch deployment creation requires an idempotency key;
- command replay behavior remains authoritative for execution;
- partial patch installation returns per-update results and an overall terminal state; the server never marks success when any requested update failed;
- loss of NATS does not lose events because all three services use transactional outboxes;
- loss of network does not lose device records because the agent spools them.

## Certification gates

A v0.9 candidate is promotable only when all are true on the same SHA:

1. Software/Patch/Policy unit and integration tests pass.
2. Three new Docker images are non-root and migrations are reversible.
3. Device Edge route tests prove only four new device routes were added.
4. Gateway route tests prove no `/api/v1/device/*` northbound exposure.
5. Windows agent portable tests/race/vet remain green.
6. Windows CI compiles the WUA implementation and runs registry software inventory against the Windows runner without shell execution.
7. Patch provider contract tests cover scan, selected-ID install, partial failure and reboot-required semantics.
8. Policy precedence/conflict/compliance tests are exhaustive for all five target levels.
9. Web Console tests cover RBAC, tenant/site scope, empty/error/loading and typed patch/policy forms.
10. Clean-stack v0.9 from empty volumes performs: bootstrap -> tenant/site/asset -> enrollment/mTLS -> software snapshot -> patch scan -> policy resolve/compliance -> patch deployment -> typed command result -> Audit.
11. Existing v0.1-v0.8 certification workflows remain green.
12. `VERSION`, README, ROADMAP, MASTER and CHANGELOG are updated only after the candidate SHA has passed the release gates.

## Explicitly deferred to later versions

- third-party package repositories or generic package installation;
- arbitrary software uninstall;
- script deployment;
- remote interactive shell;
- Linux/macOS patch providers;
- WSUS administration/configuration;
- vulnerability scoring/DFIR correlation;
- tickets/help-client workflows.
