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
| v0.7.0 | Device Edge + Windows Agent Modern | ✅ CERTIFICADO / promoción a main |
| v0.8.0 | Web Console MVP | 🟡 SIGUIENTE GATE |
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

## v0.1–v0.5 — Core servidor

- [x] Identity: bootstrap, Argon2, JWT Ed25519/JWKS, RBAC.
- [x] Tenant: empresas, membresías, sedes, departamentos y autorización tenant-scoped.
- [x] Asset: inventario canónico, IDs externos y referencias Tenant validadas por API.
- [x] Enrollment: token one-time, reserva idempotente, CSR y device identity.
- [x] PKI: Root/Intermediate, emisión, revocación, CRL y rotación.
- [x] Gateway: allowlist estática, JWT, sanitización, límites y rate-limit.
- [x] Audit: BD independiente, dedupe, append-only y hash chain.
- [x] Docker/Compose y clean-stack certificados.

## v0.6.0 — Endpoint Operations Core — DONE

- [x] Agent Control: heartbeat, capabilities, binding tenant/asset/device, online/offline.
- [x] API device-facing con principal normalizado.
- [x] outbox + `device.online`, `device.offline`, `device.capabilities.changed`.
- [x] Command Service: allowlist, idempotencia, leases, acquire/running/result/cancel.
- [x] replay idéntico idempotente y cross-device protegido.
- [x] Telemetry: esquema allowlisted, batches, dedupe y latest tenant-scoped.
- [x] bases/migraciones independientes y servicios Docker non-root.
- [x] NATS/JetStream + Audit.
- [x] dos clean-stack desde volúmenes vacíos.
- [x] recuperación de outbox después de caída de NATS.
- [x] aislamiento de signing keys y CA material.

## v0.7.0 — Device Edge + Windows Agent Modern — CERTIFICADO

### Device Edge

- [x] HTTPS/mTLS con `tls.RequireAndVerifyClientCert` y TLS >=1.2.
- [x] principal derivado del URI SAN SPIFFE del certificado.
- [x] allowlist estricta de las cinco rutas device-facing.
- [x] headers de identidad/forwarding controlados por cliente eliminados.
- [x] CRL firmada, last-good y fail-closed al expirar.
- [x] CA TLS de servidor separada; private key no montada al runtime.
- [x] contenedor non-root y Compose.

### Windows Agent

- [x] servicio Windows no interactivo bajo `NT AUTHORITY\LocalService`.
- [x] enrollment local con ECDSA P-256 + CSR.
- [x] validación de chain/SPIFFE/serial/fingerprint.
- [x] private key protegida con DPAPI LocalMachine.
- [x] heartbeat + capability negotiation.
- [x] collector Windows CPU/RAM/discos y plataforma.
- [x] command acquire/execute/result para `inventory.refresh`, `device.reboot`, `service.restart`.
- [x] ejecución nativa WinAPI/SCM; sin shell remoto arbitrario.
- [x] spool offline 64 MiB/10k y resultados con prioridad.
- [x] backoff exponencial con jitter, máximo 5 min.
- [x] actualización Ed25519 firmada, SHA-256, anti-downgrade y rollback por health marker.
- [x] EXE x64 ejecutado en CI Windows.
- [x] EXE arm64 compile-gated.
- [x] MSI x64 WiX v4 + SHA256SUMS.
- [x] instalación/desinstalación MSI silenciosa.
- [x] servicio Auto + DelayedAutoStart=1, detenido hasta enrollment.
- [x] template de configuración instalado, válido y sin secretos ficticios.

### Gate de promoción v0.7

- [x] agent `go test -race` + `go vet`.
- [x] Windows test/vet/build x64 + arm64.
- [x] scans contra TLS inseguro y shell remoto.
- [x] Device Edge tests/vet/build/non-root.
- [x] Compose válido.
- [x] clean-stack v0.7 desde volúmenes vacíos.
- [x] enrollment/certificado real.
- [x] mTLS real y spoofing bloqueado.
- [x] heartbeat -> ONLINE.
- [x] telemetry -> latest.
- [x] command -> acquire -> running -> result -> replay idempotente.
- [x] revocación -> CRL -> acceso bloqueado.
- [x] CA privada de Device Edge aislada.
- [x] MSI real install/uninstall + LocalService + delayed-auto.
- [x] artifacts EXE/MSI/hashes generados.
- [x] core v0.6 protegido por regresión clean-stack.

> Compatibilidad: el target de producto es Windows 10/11 moderno. El gate automatizado ejecuta x64 en runner Windows y compila arm64. La matriz física por edición/hardware se mantiene como validación de campo y no se falsifica como evidencia automatizada.

## Gate activo — v0.8.0 Web Console MVP

Objetivo: hacer administrable visualmente el core ya certificado, sin reabrir los servicios cerrados salvo defectos demostrados.

- [ ] login real a través de Gateway.
- [ ] selector tenant/sede.
- [ ] inventario de activos y dispositivos.
- [ ] estado online/offline y telemetry básica.
- [ ] creación y seguimiento de comandos permitidos.
- [ ] visor de Audit.
- [ ] enrollment flow administrable.
- [ ] RBAC UI consistente con backend.
- [ ] estados loading/empty/error y accesibilidad.
- [ ] Docker reproducible y E2E navegador.
- [ ] clean-stack desde servidor vacío hasta operación desde UI.

## Gates posteriores

- **v0.9:** Software + Patch + Policy.
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
10. Retry/replay/idempotencia probados cuando aplique.
11. CI verde sobre el mismo SHA candidato.
12. Documentación actualizada antes de promoción.

## Gate Core MVP

Una instalación limpia ya puede:

- [x] iniciar servidor completo;
- [x] crear/autenticar `platform_admin`;
- [x] crear empresa/sede/departamento/activo;
- [x] enrolar endpoint y emitir certificado;
- [x] instalar Windows Agent;
- [x] autenticar endpoint por mTLS y mostrar ONLINE;
- [x] recibir telemetry del pipeline Windows;
- [x] ejecutar comando permitido y recibir resultado idempotente;
- [x] consultar lifecycle en Audit;
- [x] sobrevivir red intermitente mediante spool/retry;
- [x] update/rollback transaccional del agente;
- [ ] administrar todo desde Web Console.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos se implementan mediante una matriz de capacidades separada. No se simula paridad donde la plataforma no la permite.
