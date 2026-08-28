# IT Guardian — MASTER

**Producto:** Sistema Central de Administración Empresarial de TI  
**Nombre:** IT Guardian  
**Repositorio:** `LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI`  
**Arquitectura:** microservicios independientes + agentes por plataforma + Web Console BFF  
**Release del core:** `v0.8.0` certificado  
**Gate activo:** `v0.9.0 Software + Patch + Policy`  
**Objetivo:** `v1.0.0 Enterprise Stable`

## 1. Propósito

IT Guardian es una plataforma self-hosted para administrar identidades, sedes, activos, endpoints, servidores, móviles, impresoras, red, seguridad, soporte, backup y automatización. Cada dominio se construye y versiona de forma independiente; un servicio cerrado no se reabre salvo bug demostrado o contrato nuevo explícitamente versionado.

Cada activo recibe un `guardian_asset_id` estable y puede correlacionarse con identificadores externos. Los motores OSS son adaptadores/backends reemplazables, no la UX final.

## 2. Principios no negociables

1. Base de datos por dominio; no hay escritura cruzada entre microservicios.
2. TDD para comportamiento nuevo y gates E2E antes de DONE.
3. Zero-trust entre dominios y endpoint/servidor.
4. Secret safety por allowlist; tokens/private keys no entran a logs/eventos/audit.
5. Mínimo privilegio y runtime non-root cuando aplique.
6. Private keys de endpoints se generan y permanecen en el dispositivo.
7. Operación offline durable para endpoints.
8. No existe shell remoto arbitrario como primitive del core.
9. Compatibilidad explícita por plataforma; no se simula paridad.
10. SemVer, changelog y CI sobre el SHA promovido.
11. El navegador nunca recibe bearer/refresh tokens de Identity.
12. Scope tenant/sede de Web Console se conserva solo en memoria y las consultas backend siguen tenant-scoped.

## 3. Arquitectura certificada hasta v0.8

```text
                             ADMIN PLANE
Browser
  |
  v
Web Console React/TS + BFF :8088 ---- Valkey interno
  |
  v
Gateway :8080
  |
  +-- Identity :8001
  +-- Tenant :8002
  +-- Asset :8003
  +-- PKI :8004
  +-- Enrollment :8005
  +-- Audit :8006
  +-- Agent Control :8007
  +-- Command :8008
  +-- Telemetry :8009

                            DEVICE PLANE
Windows Agent Modern
  |
  | HTTPS + mTLS / X.509 SPIFFE
  v
Device Edge :8443
  +-- Agent Control
  +-- Command
  +-- Telemetry

Domains <---- NATS JetStream ----> Workers ----> Audit
Domains ----> PostgreSQL independiente por dominio
```

Gateway no expone rutas device-facing. Web Console BFF solo proxifica una allowlist administrativa. Device Edge termina mTLS, valida CRL, deriva identidad del certificado y solo proxifica la allowlist endpoint.

## 4. Núcleo implementado

1. `identity-service`: usuarios, credenciales, JWT Ed25519/JWKS y RBAC.
2. `tenant-service`: organizaciones, sedes, departamentos y membresías.
3. `asset-service`: modelo canónico de activos y correlación externa.
4. `enrollment-service`: tokens one-time, reserva e identidad de dispositivo.
5. `pki-service`: CA, emisión, rotación, revocación y CRL.
6. `gateway-service`: borde administrativo allowlisted.
7. `audit-service`: auditoría append-only/tamper-evident.
8. `agent-control-service`: heartbeat, capabilities y online/offline.
9. `command-service`: jobs tipados, leases y resultados idempotentes.
10. `telemetry-service`: ingestión allowlisted, dedupe y latest.
11. `device-edge-service`: borde mTLS, X.509/SPIFFE y CRL.
12. `windows-agent`: servicio endpoint, DPAPI, telemetry, commands, spool y updater firmado.
13. `web-console-service`: BFF administrativo, sesión server-side, CSRF, CSP y SPA runtime.
14. `apps/web-console`: React/TypeScript para operación visual del core.

## 5. Windows Agent v0.7

Target moderno: Windows 10/11 y Windows Server modernos. Evidencia automatizada: x64 ejecutado en runner Windows y arm64 compile-gated.

- servicio `ITGuardianAgent` bajo LocalService;
- MSI x64 Auto + delayed-auto, detenido hasta enrollment;
- ECDSA P-256 + CSR local;
- private key DPAPI LocalMachine;
- mTLS hacia Device Edge;
- CPU/RAM/discos;
- `inventory.refresh`, `device.reboot`, `service.restart`;
- WinAPI/SCM directo, sin shell remoto;
- spool 64 MiB/10k y retry/backoff;
- updater Ed25519, HTTPS, SHA-256, anti-downgrade y rollback.

## 6. Web Console v0.8

Superficie implementada: Overview, Organization, Assets, Devices, Device Detail, Commands, Enrollment, Audit y Users.

Seguridad:

- login/logout mediante BFF -> Gateway;
- bearer/refresh tokens solo server-side;
- cookie opaca HttpOnly/SameSite=Strict/Secure en producción;
- Valkey de sesiones interno;
- CSRF para mutaciones;
- CSP, frame deny, nosniff, no-referrer y permissions policy;
- no-store para BFF API;
- sin tokens/scope persistidos en Web Storage;
- allowlist fija; no proxy catch-all;
- device plane inaccesible desde Web Console;
- RBAC para navegación y URL directa;
- tenant/site selector en memoria;
- Assets/Devices/Commands/Enrollment se solicitan tenant-scoped al servidor.

## 7. Certificación v0.8

El gate Chromium clean-stack parte de volúmenes vacíos, crea admin/tenant/sede/departamento/activo, enrola endpoint y obtiene certificado. El endpoint reporta heartbeat/telemetry por Device Edge mTLS. Chromium inicia sesión, fija scope, abre el dispositivo, comprueba telemetry, crea un comando, el agente mTLS lo adquiere y sube `SUCCEEDED`, Audit refleja el lifecycle y logout elimina la sesión del navegador. CI también valida non-root, Valkey interno y boundary del BFF/Gateway.

## 8. Eventos canónicos

Incluyen `identity.user.*`, `tenant.*`, `asset.*`, `enrollment.token.*`, `device.enrolled`, `device.enrollment.failed`, `pki.certificate.*`, `device.online`, `device.offline`, `device.capabilities.changed`, lifecycle `command.*` y `telemetry.batch.accepted`.

## 9. Plataformas objetivo

### Servidor
- Linux x86_64/arm64 con Docker/Compose recomendado para producción.
- Windows Docker Desktop/WSL2 y macOS Docker Desktop para laboratorio/compatibilidad.

### Consola
- Web React + TypeScript: certificada en v0.8.
- Desktop Tauri: gate posterior cuando corresponda.

### Agentes
- Windows 10/11 moderno: v0.7 Modern.
- Windows 7/8/8.1: Legacy separado.
- Linux/macOS modernos: v0.13.
- macOS Lion–10.12: legacy separado.
- Android/iOS/Huawei/KaiOS/Symbian: gates posteriores.

## 10. Dominios posteriores

### v0.9 Endpoint RMM básico
`software-service`, `patch-service`, `policy-service`.

### Endpoint operations posteriores
`remote-support-service`, `usb-service`, `backup-service`.

### Seguridad
`security-service`, `vulnerability-service`, `forensic-service`.

### Red e infraestructura
`network-service`, `wifi-service`, `vpn-service`, `printer-service`, `site-collector-service`, `server-service`.

### Movilidad
`mobile-service`, MDM Android/Apple/Huawei y `location-service`.

### ITSM/negocio TI
`ticket-service`, `notification-service`, `license-service`, `report-service`, `automation-service`, `integration-service`.

## 11. UX actual/objetivo

v0.8 cubre Overview, Organization, Assets, Devices, Commands, Enrollment, Audit y Users. Gates posteriores agregan Operations/Software/Patch/Policy, Security, Network, Service Desk, Automation, Reports, Integrations y Settings sin romper la navegación/RBAC existente.

## 12. Políticas offline

El endpoint mantiene identidad/spool local. Una caída de red no reejecuta un comando ya ejecutado solo porque falló el upload del resultado. Resultados terminales tienen prioridad sobre telemetry.

## 13. Definition of DONE

Contrato/runtime real, auth explícita, persistencia/migraciones cuando aplique, observabilidad, Docker/installer, tests, secret isolation, E2E, clean-stack, idempotencia/replay, documentación y CI verde sobre el mismo SHA.

## 14. Versionado vigente

- `v0.1.0`: Foundation + Identity — DONE.
- `v0.2.0`: Tenant — DONE.
- `v0.3.0`: Asset — DONE.
- `v0.4.0`: Enrollment + PKI — DONE.
- `v0.5.0`: Gateway + Audit — DONE.
- `v0.6.0`: Agent Control + Command + Telemetry — DONE.
- `v0.7.0`: Device Edge + Windows Agent Modern — CERTIFICADO.
- `v0.8.0`: Web Console MVP — CERTIFICADO.
- `v0.9.0`: Software + Patch + Policy — SIGUIENTE.
- `v0.10.0`: Tickets + Help Client.
- `v0.11.0`: Remote Support.
- `v0.12.0`: Security + Wazuh + USB.
- `v0.13.0`: Linux + macOS Agents.
- `v0.14.0`: Servers + Zabbix + Printers.
- `v0.15.0`: Backup.
- `v0.16.0`: Network + Wi-Fi + VPN.
- `v0.17.0`: Android/iOS MDM + Location.
- `v0.18.0`: DFIR + Vulnerability.
- `v0.19.0`: Automation + Reports + Licensing.
- `v0.20.0-rc`: Release Candidate integral.
- `v1.0.0`: Enterprise Stable.

## 15. Gate activo: v0.9 Software + Patch + Policy

Se construyen tres dominios independientes con collectors/executors nativos Windows, targeting y compliance. No se introduce shell remoto arbitrario. Cada dominio tendrá migración, Docker, Gateway/BFF/UI y E2E antes de DONE.

## 16. Regla de construcción

`Diseño -> test RED -> implementación GREEN -> integración -> seguridad -> packaging -> E2E -> documentación -> CI -> DONE -> siguiente gate`.
