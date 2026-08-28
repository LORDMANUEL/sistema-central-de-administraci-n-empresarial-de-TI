# IT Guardian — Roadmap de producto

Regla de entrega: **cada versión agrega una capacidad utilizable de punta a punta**. Ningún servicio se marca DONE solo por tener código o unit tests.

## Camino crítico Core MVP

`Identity -> Tenant -> Asset -> Enrollment/PKI -> Gateway/Audit -> Agent Control/Command/Telemetry -> Device Edge/Windows Agent -> Web Console`

## Estado real de versiones

| Versión | Entrega | Estado |
|---|---|---|
| v0.1.0 | Foundation + Identity | ✅ DONE / main |
| v0.2.0 | Tenant | ✅ DONE / main |
| v0.3.0 | Asset Service | ✅ DONE / main |
| v0.4.0 | Enrollment + PKI | ✅ DONE / main |
| v0.5.0 | Gateway + Audit | ✅ DONE / main |
| v0.6.0 | Agent Control + Command + Telemetry | ✅ DONE / main |
| v0.7.0 | Device Edge + Windows Agent Modern | ✅ CERTIFICADO / main |
| v0.8.0 | Web Console MVP | ✅ CERTIFICADO / promoción a main |
| v0.9.0 | Software + Patch + Policy | 🟡 SIGUIENTE GATE |
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

## v0.1–v0.5 — Core servidor — DONE

- [x] Identity: bootstrap, Argon2, JWT Ed25519/JWKS, RBAC.
- [x] Tenant: empresas, membresías, sedes, departamentos y autorización tenant-scoped.
- [x] Asset: inventario canónico, IDs externos y referencias Tenant validadas.
- [x] Enrollment: token one-time, reserva idempotente, CSR y device identity.
- [x] PKI: Root/Intermediate, emisión, revocación, CRL y rotación.
- [x] Gateway: allowlist estática, JWT, sanitización, límites y rate-limit.
- [x] Audit: BD independiente, dedupe, append-only y hash chain.
- [x] Docker/Compose y clean-stack certificados.

## v0.6.0 — Endpoint Operations Core — DONE

- [x] heartbeat/capabilities/online-offline.
- [x] comandos tipados, idempotencia, leases y resultados.
- [x] telemetry allowlisted, batches, dedupe y latest.
- [x] NATS/JetStream + Audit.
- [x] bases/migraciones independientes y Docker non-root.
- [x] clean-stack y recuperación de outbox.

## v0.7.0 — Device Edge + Windows Agent Modern — CERTIFICADO

- [x] Device Edge HTTPS/mTLS, SPIFFE, allowlist, CRL fail-closed y non-root.
- [x] CA TLS de servidor separada del runtime.
- [x] Windows service LocalService.
- [x] enrollment ECDSA P-256, chain/SPIFFE/serial/fingerprint.
- [x] DPAPI LocalMachine.
- [x] heartbeat, telemetry Windows y capability negotiation.
- [x] `inventory.refresh`, `device.reboot`, `service.restart` sin shell remoto.
- [x] spool offline + retry/backoff.
- [x] updater Ed25519 + SHA-256 + rollback.
- [x] EXE x64/arm64, MSI x64 y hashes.
- [x] Windows CI, install/uninstall y clean-stack mTLS.

## v0.8.0 — Web Console MVP — CERTIFICADO

Objetivo cumplido: administrar visualmente el core ya certificado sin exponer credenciales o el device plane al navegador.

- [x] login/logout real a través de Web Console BFF -> Gateway.
- [x] sesión opaca HttpOnly y tokens Identity server-side.
- [x] Valkey/Redis de sesiones obligatorio en producción e interno a Compose.
- [x] CSRF + CSP + headers de hardening + no-store.
- [x] selector tenant/sede en memoria.
- [x] requests operativas server-side tenant-scoped.
- [x] inventario de activos y dispositivos.
- [x] detalle endpoint, estado online/offline y telemetry básica.
- [x] creación/seguimiento/cancelación de comandos permitidos.
- [x] visor/verificación de Audit.
- [x] enrollment flow administrable.
- [x] RBAC de navegación y URL directa.
- [x] estados loading/empty/error.
- [x] Docker reproducible non-root.
- [x] Valkey no expuesto al host.
- [x] Playwright Chromium E2E.
- [x] clean-stack desde volúmenes vacíos.
- [x] endpoint real enrolado con certificado mTLS.
- [x] heartbeat ONLINE + telemetry real.
- [x] comando UI -> Device Edge -> agente mTLS -> `SUCCEEDED`.
- [x] lifecycle visible en Audit.
- [x] logout y borrado de cookie.
- [x] aislamiento runtime.

## Gate activo — v0.9.0 Software + Patch + Policy

Objetivo: añadir RMM básico como tres dominios independientes sin reabrir el core salvo contratos versionados necesarios.

- [ ] Software Inventory Service y snapshots por endpoint.
- [ ] collector Windows nativo de software instalado.
- [ ] Patch Service y catálogo/estado de actualizaciones.
- [ ] integración Windows Update Agent sin shell arbitrario.
- [ ] Policy Service versionado.
- [ ] targeting tenant/sede/departamento/dispositivo.
- [ ] compliance/resultados y Audit.
- [ ] contratos agent/device allowlisted.
- [ ] Gateway/BFF/Web Console para Software/Patch/Policy.
- [ ] Docker/migraciones/observabilidad por dominio.
- [ ] clean-stack/E2E v0.9 y regresión v0.8.

## Gates posteriores

- **v0.10:** Tickets + Help Client.
- **v0.11:** Remote Support.
- **v0.12:** Security/Wazuh/USB.
- **v0.13:** Linux + macOS Agents.
- **v0.14:** Servers/Zabbix/Printers.
- **v0.15:** Backup.
- **v0.16:** Network/Wi-Fi/VPN.
- **v0.17:** Android/iOS MDM + Location.
- **v0.18:** DFIR + Vulnerability.
- **v0.19:** Automation + Reports + Licensing.
- **v0.20.0-rc:** integración/hardening final.
- **v1.0.0:** Enterprise Stable.

## Definition of Done

1. Runtime real y errores normalizados.
2. Autenticación/autorización explícita.
3. Persistencia/migraciones cuando aplique.
4. Health/readiness/observabilidad cuando aplique.
5. Docker non-root o instalador de plataforma.
6. Tests unitarios/integración.
7. Seguridad/secret isolation.
8. E2E con servicios anteriores.
9. Instalación limpia reproducible.
10. Retry/replay/idempotencia cuando aplique.
11. CI verde sobre el mismo SHA candidato.
12. Documentación actualizada antes de promoción.

## Gate Core MVP

- [x] iniciar servidor completo;
- [x] crear/autenticar `platform_admin`;
- [x] crear empresa/sede/departamento/activo;
- [x] enrolar endpoint y emitir certificado;
- [x] instalar Windows Agent;
- [x] autenticar endpoint por mTLS y mostrar ONLINE;
- [x] recibir telemetry Windows;
- [x] ejecutar comando permitido y recibir resultado idempotente;
- [x] consultar lifecycle en Audit;
- [x] sobrevivir red intermitente mediante spool/retry;
- [x] update/rollback transaccional del agente;
- [x] administrar el core desde Web Console.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos se implementan mediante una matriz de capacidades separada. No se simula paridad donde la plataforma no la permite.
