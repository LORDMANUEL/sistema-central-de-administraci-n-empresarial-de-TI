# IT Guardian — Roadmap de producto

Regla de entrega: **cada versión debe agregar una capacidad utilizable de punta a punta**.

## Camino crítico Core MVP

`Identity -> Tenant -> Asset -> Enrollment/PKI -> Gateway/Audit -> Agent Control/Command/Telemetry -> Windows Agent -> Web Console`

## Estado de versiones

| Versión | Entrega | Estado |
|---|---|---|
| v0.1.0 | Foundation + Identity | ✅ DONE / main |
| v0.2.0 | Tenant | ✅ DONE / main |
| v0.3.0 | Asset Service | 🟠 RC CERTIFICADO — PR #3 listo; merge a `main` pendiente |
| v0.4.0 | Enrollment + PKI | 🟡 DESARROLLO APILADO permitido; promoción bloqueada por merge v0.3 |
| v0.5.0 | Gateway + Audit | ⬜ PENDIENTE |
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

## v0.3.0 Asset Service — gate actual

- [x] Modelo canónico de activos.
- [x] `guardian_asset_id` estable.
- [x] Correlación de IDs externos.
- [x] API `/api/v1`.
- [x] PostgreSQL de dominio independiente.
- [x] Transactional outbox.
- [x] Publicador NATS JetStream idempotente.
- [x] Outbox resiliente: `attempts`, `last_error`, ACK antes de `published_at`, sin hot-loop por evento.
- [x] Envelope de eventos común y versionado (`schema_version=1`).
- [x] JWT Ed25519/JWKS.
- [x] Health/readiness/métricas/request ID.
- [x] Alembic.
- [x] Docker no-root.
- [x] CI base: tests + migración + Docker build + Compose config.
- [x] Política tenant-scoped por TDD: platform_admin global, org_admin escritura, membresía activa lectura, tenant suspendido denegado.
- [x] Resolución tenant-scoped contra Tenant Service sin compartir BD.
- [x] Validación tenant/site/department antes de persistir referencias.
- [x] E2E `Identity -> Tenant -> Asset`.
- [x] E2E `Asset -> Outbox -> NATS JetStream`.
- [x] Instalación limpia del stack en CI con `docker compose up -d --build` y teardown completo.
- [x] CI final verde sobre el SHA RC de runtime `bd411ff593006c52b5a205867616e76d2c2043c3`.
- [x] PR #3 listo para review.
- [ ] Merge a `main`.
- [ ] Marcar v0.3.0 DONE.

## Definition of Done

1. API `/api/v1` y errores normalizados.
2. Autenticación/autorización explícita.
3. Base de datos propia del dominio.
4. Alembic `upgrade -> downgrade -> upgrade`.
5. Health/readiness, Prometheus y `request_id`.
6. Docker no-root y Compose.
7. Tests unitarios e integración verdes.
8. Transactional outbox para eventos.
9. CI: compile, tests, imagen y Compose.
10. Documentación y notas de seguridad.
11. Integración con el servicio anterior.
12. Cero mocks/endpoints vacíos en producción.

## Gate Core MVP

Una instalación limpia debe poder: iniciar Compose; crear/autenticar `platform_admin`; crear empresa/sede/activo; enrolar e instalar un agente Windows; recibir heartbeat e inventario; ejecutar un comando; recibir resultado; y consultar auditoría desde Web Console.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos usan una matriz de capacidades separada y no bloquean el núcleo moderno salvo requisito expreso de release.
