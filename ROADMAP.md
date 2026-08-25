# IT Guardian — Roadmap de producto

Regla de entrega: **cada versión debe agregar una capacidad utilizable de punta a punta**.

## Camino crítico Core MVP

`Identity -> Tenant -> Asset -> Enrollment/PKI -> Gateway/Audit -> Agent Control/Command/Telemetry -> Windows Agent -> Web Console`

## Estado de versiones

| Versión | Entrega | Estado |
|---|---|---|
| v0.1.0 | Foundation + Identity | ✅ DONE / main |
| v0.2.0 | Tenant | ✅ DONE / main |
| v0.3.0 | Asset Service | ✅ DONE / main |
| v0.4.0 | Enrollment + PKI | 🟢 CERTIFICADO — PR #6 listo para promoción a `main` |
| v0.5.0 | Gateway + Audit | 🟡 SIGUIENTE — análisis/diseño tras merge v0.4 |
| v0.6.0 | Agent Control + Command + Telemetry | ⬜ PENDIENTE |
| v0.7.0 | Windows Agent Modern | ⬜ PENDIENTE |
| v0.8.0 | Web Console MVP | ⬜ PENDIENTE |
| v0.9.0 | Software + Patch + Policy | ⬜ PENDIENTE |
| v0.10.0 | Tickets + Help Client | ⬜ PENDIENTE |
| v0.11.0 | Remote Support | ⬜ PENDIENTE |
| v0.12.0 | Security + Wazuh + USB | ⬜ PENDIENTE |
| v0.13.0 | Linux + macOS Agents | ⬜ PENDIENTE |
| v0.14.0 | Servers + Zabbix + Printers | ⬜ PENDIENTE |
| v0.15.0 | Backup | ⬜ PENDIENTE |
| v0.16.0 | Network + Wi-Fi + VPN | ⬜ PENDIENTE |
| v0.17.0 | Android/iOS MDM + Location | ⬜ PENDIENTE |
| v0.18.0 | DFIR + Vulnerability | ⬜ PENDIENTE |
| v0.19.0 | Automation + Reports + Licensing | ⬜ PENDIENTE |
| v0.20.0-rc | Release Candidate | ⬜ PENDIENTE |
| v1.0.0 | Enterprise Stable | ⬜ PENDIENTE |

## v0.3.0 Asset Service — DONE

- [x] Modelo canónico de activos y `guardian_asset_id` estable.
- [x] Correlación de IDs externos.
- [x] API `/api/v1` y BD `guardian_asset` independiente.
- [x] Tenant-scoped authorization sin compartir BD.
- [x] Validación tenant/site/department antes de persistir.
- [x] Transactional outbox + JetStream idempotente y resiliente.
- [x] JWT Ed25519/JWKS.
- [x] Health/readiness/métricas/request ID.
- [x] Alembic y Docker no-root.
- [x] E2E `Identity -> Tenant -> Asset -> JetStream`.
- [x] Instalación limpia y teardown completo en CI.
- [x] PR #3 mergeado a `main` el 2026-08-24.

## v0.4.0 PKI — CERTIFICADO

- [x] Root CA RSA-4096 + Device Intermediate RSA-3072.
- [x] Inicialización idempotente y fail-safe; no sobreescribe CA inconsistente/parcial.
- [x] Root private key disponible únicamente para `pki-ca-init`.
- [x] Runtime API monta solo Intermediate online read-only; worker no monta material CA.
- [x] Device private key nunca cruza la API.
- [x] CSR RSA >=2048 y EC P-256/P-384; claves débiles/no soportadas rechazadas.
- [x] Certificado cliente con CA=false, CLIENT_AUTH, SKI/AKI y SAN Guardian.
- [x] Grants Enrollment Ed25519 <=120 s ligados a tenant/asset/device/issuance/CSR.
- [x] Emisión idempotente por `issuance_id`.
- [x] Administración Identity + Tenant (`platform_admin`/`org_admin`).
- [x] Revocación persistente e idempotente.
- [x] CRL firmada con seriales revocados.
- [x] Rotación atómica con nueva clave obligatoria y anterior `superseded`.
- [x] Transactional outbox `pki.certificate.*` + JetStream.
- [x] Prometheus, request_id y logs secret-safe.
- [x] Alembic + BD `guardian_pki`.
- [x] Docker no-root + Compose.
- [x] Tests/compile/migration round-trip verdes.
- [x] Clean-stack `pki-smoke`: emisión -> revocación -> CRL -> JetStream.
- [x] Smoke verifica aislamiento Root key y Enrollment signer.
- [x] Smoke verifica CA init idempotente y teardown de volúmenes.

## v0.4.0 Enrollment — CERTIFICADO

Flujo certificado:

`enrollment token -> validar tenant/asset -> reservar device/issuance -> CSR -> grant PKI <=120 s -> certificado -> token CONSUMED -> device ENROLLED -> JetStream`

- [x] Modelo `EnrollmentToken` one-time/expirable/tenant-scoped.
- [x] Modelo `DeviceEnrollment` con `device_id` estable y vínculo a `guardian_asset_id`.
- [x] Token almacenado solo como hash; valor plaintext solo se entrega al crearlo.
- [x] Administración Identity + Tenant (`platform_admin`/`org_admin`).
- [x] Validación de Asset mediante API de Asset Service, sin leer su BD.
- [x] Reserva atómica one-time y protección frente a replay/carreras.
- [x] Retry idéntico RESERVED/CONSUMED conserva `device_id` e `issuance_id`.
- [x] CSR recibido desde endpoint; private key permanece en dispositivo.
- [x] Enrollment signer Ed25519 separado con JWKS público.
- [x] Grant PKI `certificate_issue` <=120 s ligado a CSR/device/tenant/asset/issuance.
- [x] Cliente PKI con retries seguros/idempotentes por `issuance_id`.
- [x] Recuperación: red/5xx y `issuance_conflict` conservan reserva/IDs; rechazo corregible libera token solo sin certificado.
- [x] Estado persistente PENDING / FAILED / ENROLLED y token ACTIVE / RESERVED / CONSUMED / REVOKED / EXPIRED.
- [x] Transactional outbox `enrollment.token.created`, `enrollment.token.revoked`, `device.enrolled`, `device.enrollment.failed`.
- [x] Health/readiness/métricas/request_id/logging secret-safe.
- [x] Alembic + BD `guardian_enrollment` independiente.
- [x] Docker no-root + Compose en puerto 8005.
- [x] Worker Enrollment sin `ENROLLMENT_SIGNING_KEY` y sin material CA.
- [x] Tests unitarios/integración + migration round-trip.
- [x] E2E limpio `Identity -> Tenant -> Asset -> Enrollment -> PKI -> certificate -> JetStream`.
- [x] Token replay distinto rechazado con 409.
- [x] Retry consumido devuelve mismo device/certificado sin nueva llamada PKI.
- [x] Certificado X.509 real verificado con OpenSSL.
- [x] `device.enrolled` verificado en JetStream sin token/CSR.
- [x] Aislamiento signer/CA verificado por `docker inspect`.
- [x] Teardown completo de contenedores y volúmenes.
- [x] Identity/Tenant/Asset/Enrollment/PKI CI verdes sobre el mismo SHA candidato.
- [x] PR #6 técnicamente listo para promoción a `main`.

## Siguiente gate — v0.5.0 Gateway + Audit

Antes de implementar se debe cerrar especificación y threat model. El alcance no incluye todavía Agent Control/Command/Telemetry.

Objetivos mínimos:

- [ ] Gateway como borde HTTP controlado con allowlist de rutas/servicios.
- [ ] Propagación de `request_id` y contexto sin confiar en headers de identidad inyectables por cliente.
- [ ] Validación JWT en el borde sin eliminar authn/authz de cada microservicio.
- [ ] Límites de body/header, timeouts y rate limiting por ruta/actor/tenant.
- [ ] Política explícita de retries: no repetir mutaciones no idempotentes.
- [ ] Audit Service con BD `guardian_audit` propia y API solo lectura administrativa.
- [ ] Ingesta idempotente de eventos de `GUARDIAN_EVENTS` por `event_id` único.
- [ ] Registro de acciones de gateway que no generan eventos de dominio, incluidos rechazos relevantes.
- [ ] Modelo append-only con evidencia de manipulación (`prev_hash`/`record_hash` o esquema equivalente validado).
- [ ] Metadata de auditoría por allowlist; nunca bearer, password, enrollment token, CSR, private key ni signing seed.
- [ ] `platform_admin` global y lectura tenant-scoped para `org_admin` activo.
- [ ] Tests de aislamiento cross-tenant, dedupe, hash-chain/tamper y secret safety.
- [ ] Docker no-root, migración round-trip, Compose y clean-stack E2E.

## Definition of Done

1. API `/api/v1` y errores normalizados.
2. Autenticación/autorización explícita.
3. Base de datos propia del dominio.
4. Alembic `upgrade -> downgrade -> upgrade`.
5. Health/readiness, Prometheus y `request_id`.
6. Docker no-root y Compose.
7. Tests unitarios e integración verdes.
8. Transactional outbox para eventos cuando el dominio emita eventos.
9. CI: compile, tests, imagen y Compose.
10. Documentación y notas de seguridad.
11. Integración E2E con servicios anteriores.
12. Cero mocks/endpoints vacíos en producción.
13. Instalación limpia reproducible desde volúmenes vacíos.
14. Retry/replay/idempotencia probados cuando el dominio lo requiera.

## Gate Core MVP

Una instalación limpia debe poder: iniciar Compose; crear/autenticar `platform_admin`; crear empresa/sede/activo; enrolar e instalar un agente Windows; recibir heartbeat e inventario; ejecutar un comando; recibir resultado; y consultar auditoría desde Web Console.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos usan una matriz de capacidades separada y no bloquean el núcleo moderno salvo requisito expreso de release.
