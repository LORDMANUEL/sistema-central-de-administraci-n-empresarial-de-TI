# IT Guardian — Roadmap de producto

Regla de entrega: **cada versión debe agregar una capacidad utilizable de punta a punta**. Ningún servicio se marca DONE solo por tener código o unit tests.

## Camino crítico Core MVP

`Identity -> Tenant -> Asset -> Enrollment/PKI -> Gateway/Audit -> Agent Control/Command/Telemetry -> Windows Agent -> Web Console`

## Estado real de versiones

| Versión | Entrega | Estado |
|---|---|---|
| v0.1.0 | Foundation + Identity | ✅ DONE / main |
| v0.2.0 | Tenant | ✅ DONE / main |
| v0.3.0 | Asset Service | ✅ DONE / main |
| v0.4.0 | Enrollment + PKI | ✅ DONE / main |
| v0.5.0 | Gateway + Audit | ✅ DONE / main — PR #7 mergeado |
| v0.6.0 | Agent Control + Command + Telemetry | 🟡 EN DESARROLLO — PR #8 draft |
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
| v0.20.0-rc | Release Candidate integral | ⬜ PENDIENTE |
| v1.0.0 | Enterprise Stable | ⬜ PENDIENTE |

## v0.1–v0.5 — Core servidor estable

- [x] Identity: bootstrap, Argon2, JWT Ed25519/JWKS, RBAC.
- [x] Tenant: empresas, membresías, sedes, departamentos y tenant authorization.
- [x] Asset: inventario canónico, IDs externos y referencias Tenant validadas por API.
- [x] Enrollment: token one-time, reserva idempotente y device identity.
- [x] PKI: Root/Intermediate, CSR, emisión, revocación, CRL y rotación.
- [x] NATS JetStream y transactional outbox donde corresponde.
- [x] Gateway: allowlist estática, JWT, sanitización de headers, límites, rate-limit y proxy seguro.
- [x] Gateway: mutaciones administrativas fail-closed si Audit/NATS no confirma intención.
- [x] Audit: BD independiente, dedupe, append-only, hash chain y consulta administrativa.
- [x] Docker/Compose para el core v0.5.
- [x] Clean-stack y E2E certificados para los releases integrados antes de merge.

## Gate activo — v0.6.0 Endpoint Operations Core

Objetivo: cerrar comunicación durable entre servidor y endpoint antes de escribir el agente Windows real.

### Agent Control

- [x] modelo de heartbeat y binding tenant/asset/device.
- [x] capacidades normalizadas y transición online.
- [x] detección de offline básica.
- [ ] API autenticada por identidad de dispositivo confiable.
- [ ] transactional outbox + eventos `device.online`, `device.offline`, `device.capabilities.changed`.
- [ ] Alembic + BD `guardian_agent_control`.
- [ ] Docker no-root + Compose.
- [ ] métricas/logs/request ID.
- [ ] E2E desde Enrollment/certificado hasta heartbeat.

### Command Service

- [x] allowlist inicial: `inventory.refresh`, `device.reboot`, `service.restart`.
- [x] creación idempotente por tenant + idempotency key.
- [x] adquisición aislada por tenant/asset/device en construcción y bajo CI.
- [ ] leases expirables y reacquisition segura.
- [ ] result state machine monotónica.
- [ ] replay idéntico idempotente / replay conflictivo rechazado.
- [ ] admin API create/get/list/cancel.
- [ ] device API acquire/running/result.
- [ ] transactional outbox + wake-up subject por device.
- [ ] Alembic + BD `guardian_command`.
- [ ] Docker no-root + Compose.
- [ ] auth/metrics/logs/request ID.
- [ ] E2E command -> device simulator -> result -> Audit.

### Telemetry Service

- [x] esquema inicial de métricas permitido.
- [x] ingestión/dedupe inicial.
- [ ] API device-facing autenticada.
- [ ] latest read administrativa tenant-scoped.
- [ ] límites de tamaño/frecuencia y rechazo de métricas arbitrarias.
- [ ] Alembic + BD `guardian_telemetry`.
- [ ] Docker no-root + Compose.
- [ ] observabilidad y outbox/eventos cuando corresponda.
- [ ] E2E con simulador de dispositivo.

### Gate de promoción v0.6

- [ ] Agent Control CI completo verde.
- [ ] Command CI completo verde.
- [ ] Telemetry CI completo verde.
- [ ] todos los CI previos v0.1–v0.5 verdes sobre el mismo SHA candidato.
- [ ] `docker compose config` válido.
- [ ] instalación limpia desde volúmenes vacíos.
- [ ] simulador enrolado usa identidad de dispositivo y no headers elegidos por cliente.
- [ ] heartbeat -> online -> telemetry -> command -> result funciona de punta a punta.
- [ ] eventos aparecen en JetStream.
- [ ] acciones administrativas aparecen en Audit.
- [ ] secret scan y aislamiento de claves/certificados aprobados.
- [ ] teardown completo.
- [ ] PR #8 fuera de draft solo después de todos los puntos anteriores.

## v0.7.0 — Windows Agent Modern

Primer binario real de endpoint. No se marca DONE hasta producir artefactos reproducibles.

- [ ] servicio Windows no interactivo y usuario de privilegio mínimo.
- [ ] enrollment local con generación de private key + CSR.
- [ ] almacenamiento seguro de certificado/clave.
- [ ] heartbeat y capability negotiation.
- [ ] CPU/RAM/disco/SO + inventario base.
- [ ] command acquire/execute/result para allowlist v0.6.
- [ ] spool local offline + retry con backoff.
- [ ] actualización firmada + rollback.
- [ ] MSI/EXE versionado y hash publicado por CI.
- [ ] pruebas Windows 10/11 modernas.
- [ ] matriz legacy Windows 7/8/8.1 separada.

## v0.8.0 — Web Console MVP

- [ ] login real por Gateway.
- [ ] selector tenant/sede.
- [ ] inventario de activos/dispositivos.
- [ ] estado online/offline y telemetry básica.
- [ ] creación/seguimiento de comandos permitidos.
- [ ] visor Audit.
- [ ] enrollment flow administrable.
- [ ] RBAC UI consistente con backend.
- [ ] build Docker reproducible y E2E navegador.

## Definition of Done por microservicio

1. API/runtime real y errores normalizados.
2. Autenticación/autorización explícita.
3. Base de datos propia cuando persista estado.
4. Alembic `upgrade -> downgrade -> upgrade` cuando aplique.
5. `/health/live`, `/health/ready`, Prometheus y `request_id`.
6. Docker no-root y Compose.
7. Tests unitarios e integración verdes.
8. Transactional outbox cuando emita eventos de dominio.
9. CI: compile, tests, imagen, migraciones y Compose según aplique.
10. Documentación operativa y notas de seguridad.
11. Integración E2E con los servicios anteriores.
12. Cero mocks/endpoints vacíos declarados producción.
13. Instalación limpia reproducible desde volúmenes vacíos.
14. Retry/replay/idempotencia probados cuando aplique.
15. El servicio se prueba sobre el mismo SHA que se pretende promover.

## Gate Core MVP

Una instalación limpia debe poder:

- [ ] iniciar el servidor completo;
- [ ] crear/autenticar `platform_admin`;
- [ ] crear empresa/sede/departamento/activo;
- [ ] enrolar un endpoint y emitir certificado;
- [ ] instalar Windows Agent;
- [ ] recibir heartbeat y mostrar ONLINE;
- [ ] recibir CPU/RAM/disco/SO e inventario;
- [ ] ejecutar un comando permitido;
- [ ] recibir resultado idempotente;
- [ ] consultar la operación en Audit;
- [ ] administrar todo desde Web Console;
- [ ] actualizar/rollback sin destruir datos.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos usan una matriz de capacidades separada. No bloquean el núcleo moderno salvo requisito expreso de release.
