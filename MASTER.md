# IT Guardian — MASTER

**Producto:** Sistema Central de Administración Empresarial de TI  
**Nombre de producto:** IT Guardian  
**Repositorio:** LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI  
**Arquitectura:** Microservicios desde v0.1.0  
**Versión de trabajo:** 0.1.0-foundation  
**Objetivo de estabilidad:** v1.0.0 Enterprise Stable

## 1. Propósito

IT Guardian es una plataforma central de administración empresarial de TI, self-hosted y multiplataforma. Unifica administración, observabilidad, seguridad, soporte, inventario, movilidad, tickets, backup, red, identidad, cumplimiento y automatización en una sola experiencia web/desktop, preservando motores especializados detrás de adaptadores reemplazables.

La plataforma administra personas, identidades, sedes y activos: PCs, servidores, móviles, impresoras, switches, routers, APs, UPS, máquinas virtuales, contenedores, software, licencias, SIM/eSIM y otros dispositivos. Cada activo recibe un `guardian_asset_id` estable y puede correlacionarse con identificadores externos de Tactical RMM, Wazuh, GLPI, Zabbix, NetBox, NetBird, Velociraptor, MDM y otros motores.

## 2. Principios no negociables

1. Microservicios con límites de dominio claros; no existe una base de datos compartida modificada por múltiples servicios.
2. Cada servicio debe incluir API versionada, health/readiness, pruebas, Dockerfile, migraciones, métricas, logs estructurados y documentación antes de considerarse terminado.
3. Las operaciones de larga duración se ejecutan asíncronamente mediante workers/eventos; la UI nunca debe bloquearse esperando tareas remotas.
4. Seguridad por defecto: TLS, secretos fuera del código, RBAC, auditoría, MFA, mínimo privilegio, validación de paquetes y acciones críticas confirmables.
5. Soporte offline en endpoints: las políticas críticas siguen aplicadas sin conexión y existe recuperación administrativa temporal/auditable por dispositivo.
6. Compatibilidad explícita. Las capacidades se anuncian por plataforma; no se simula paridad donde el sistema operativo no la permite.
7. TDD para comportamiento nuevo. Ningún módulo se declara DONE sin pruebas verdes.
8. Una UX única. Los motores OSS son backends sustituibles, no la interfaz final del producto.
9. Rendimiento: feedback visual inmediato, caches y materialización de vistas; el navegador no consulta múltiples motores externos para pintar cada pantalla.
10. Versionado SemVer y changelog verificable.

## 3. Plataformas objetivo

### Servidor
- Producción recomendada: Linux x86_64/arm64 con Docker/Compose.
- Windows: Docker Desktop/WSL2 para instalaciones compatibles y laboratorio.
- macOS: Docker Desktop para desarrollo/laboratorio.

### Consola
- Web: React + TypeScript.
- Desktop: Tauri usando la misma capa visual y cliente API.
- Animación: GSAP y CSS, respetando `prefers-reduced-motion`.

### Agentes
- Windows 10/11 y Windows Server modernos: Guardian Agent Modern.
- Windows 7/8/8.1: Guardian Agent Legacy, con capacidades reducidas y estado Legacy/Risk.
- Linux: Guardian Agent Linux.
- macOS moderno: Guardian Agent Modern.
- macOS 10.7 Lion–10.12: Guardian Legacy Mac con capacidades limitadas.
- Android/Xiaomi/Android-compatible: Guardian Android + Android Enterprise/Device Owner cuando aplique.
- Huawei HarmonyOS: adaptador/agente específico separado del proveedor Android.
- iOS/iPadOS: Apple MDM + Guardian Managed App.
- KaiOS: Guardian KaiOS, capacidades según permisos disponibles.
- Symbian: Guardian Symbian Legacy, best-effort y certificado únicamente sobre hardware/toolchains validados.

### Identificadores móviles
IT Guardian diferencia explícitamente `imei/imei2`, `iccid`, `eid`, `msisdn`, `serial_number` y `gps`. Toda consulta administrativa de ubicación se audita.

## 4. Arquitectura lógica

```text
Web React/TS ─┐
Tauri Desktop ├─> API Gateway ─> Identity/Auth
Help Client ──┘       │
                      ├─> Asset Service
                      ├─> Device/Agent Control
                      ├─> Ticket Service
                      ├─> Policy Service
                      ├─> Software/Patch Service
                      ├─> Security/Vulnerability/DFIR
                      ├─> Backup
                      ├─> Network/WiFi/VPN/Printer
                      ├─> Mobile/MDM/Location
                      ├─> Automation/Notification/Audit
                      └─> Integration adapters

Services <──> NATS JetStream <──> Workers
Services ───> PostgreSQL por dominio
Objects ────> S3/MinIO compatible
Cache ──────> Redis/Valkey cuando el dominio lo necesite
```

## 5. Inventario de microservicios

### Núcleo
1. `gateway-service`: entrada HTTP/WebSocket, rate limiting, routing y contexto de tenant.
2. `identity-service`: usuarios, roles, permisos, credenciales, MFA, sesiones y tokens.
3. `tenant-service`: organizaciones, sedes, departamentos y configuración de tenancy.
4. `asset-service`: modelo canónico de activos y correlación de IDs externos.
5. `enrollment-service`: tokens de alta, aprobación y bootstrap de dispositivos.
6. `pki-service`: certificados de dispositivo, rotación y revocación.
7. `agent-control-service`: heartbeat, capacidades, comandos y resultados.
8. `telemetry-service`: ingestión de métricas, normalización y retención.
9. `command-service`: jobs remotos, idempotencia, colas y estado.
10. `audit-service`: registro inmutable de acciones administrativas y eventos sensibles.

### Operaciones endpoint
11. `software-service`: inventario, catálogo, instalación/desinstalación y versiones.
12. `patch-service`: Windows Update, Linux packages, rings y ventanas de mantenimiento.
13. `policy-service`: políticas locales, compliance y evaluación de drift.
14. `remote-support-service`: Tactical/Mesh y futuras alternativas.
15. `usb-service`: inventario, allow/deny, excepciones temporales y auditoría.
16. `backup-service`: políticas, ejecuciones, restauración y verificación.

### Seguridad
17. `security-service`: correlación Wazuh, eventos y postura.
18. `vulnerability-service`: Wazuh/Greenbone/OpenVAS y remediación.
19. `forensic-service`: Velociraptor, casos, colecciones y cadena de custodia.
20. `secrets-service-adapter`: integración con OpenBao/Vault-compatible.

### Red e infraestructura
21. `network-service`: dispositivos, interfaces y telemetría de red.
22. `wifi-service`: perfiles, FreeRADIUS/802.1X, accounting y rotación controlada.
23. `vpn-service`: NetBird/WireGuard, peers y políticas.
24. `printer-service`: SNMP/IPP, consumibles, contadores y colas/eventos.
25. `site-collector-service`: SNMPv3, IPMI, Redfish, Syslog, NetFlow/sFlow y collectors por sede.
26. `server-service`: estado de servidores, servicios, hardware y virtualización.

### Movilidad
27. `mobile-service`: inventario canónico y compliance móvil.
28. `mdm-android-service`: Android Enterprise y fabricantes compatibles.
29. `mdm-apple-service`: Apple MDM/APNs/managed devices.
30. `mdm-huawei-service`: HarmonyOS/Huawei cuando no use Android Enterprise.
31. `location-service`: ubicaciones permitidas, Lost Mode/geofencing y auditoría.

### ITSM y negocio TI
32. `ticket-service`: tickets, SLA, colas, comentarios, adjuntos y vínculo con activos.
33. `notification-service`: email, push, webhook y notificaciones internas.
34. `license-service`: licencias, asignación, expiración y utilización.
35. `report-service`: KPIs, compliance y exportaciones.
36. `automation-service`: reglas event-driven y playbooks aprobados.
37. `integration-service`: registro/estado de adaptadores externos.

## 6. Integraciones base
Tactical RMM, MeshCentral, Wazuh, Velociraptor, GLPI, Zabbix, NetBox, NetBird, FreeRADIUS, Greenbone/OpenVAS, UrBackup/Restic y OpenBao. Cada integración vive detrás de una interfaz interna y nunca expone sus credenciales al frontend.

## 7. Eventos canónicos iniciales
`identity.user.created`, `identity.user.disabled`, `device.enrolled`, `device.online`, `device.offline`, `inventory.updated`, `policy.violation`, `software.install.requested`, `software.install.completed`, `patch.required`, `backup.failed`, `usb.blocked`, `security.alert.created`, `vulnerability.detected`, `ticket.created`, `ticket.sla.at_risk`, `location.updated`, `integration.health.changed`.

## 8. UX y navegación
Overview; Assets (Computers, Servers, Mobile, Printers, Network, Virtualization); Operations (Software, Patching, Remote Support, Backup, USB); Security (Alerts, Vulnerabilities, Forensics, Compliance); Network (Topology, Wi-Fi, VPN, IPAM/DCIM); Service Desk (Tickets, SLA, Requests); Identity; Automation; Reports; Audit; Integrations; Settings.

Interacción: `Ctrl+K`, búsqueda global, panel contextual, tablas virtualizadas, WebSocket/SSE, estados skeleton/empty/error, dark/light/system, responsive, accesible y animaciones fluidas sin bloquear operaciones.

## 9. Tickets/Help Client
Aplicativo Tauri ligero para tickets con contexto autorizado del equipo, prioridad, impacto, urgencia, SLA, asignación, comentarios, adjuntos, estados, vínculo con activo y acciones remotas aprobables.

## 10. Políticas offline y privilegios
Las políticas críticas se materializan localmente. La pérdida de sincronización no elimina restricciones. `Break Glass Offline` usa desafío-respuesta firmado, expiración, auditoría y rotación posterior. No existe contraseña maestra global.

## 11. Seguridad y privacidad
MFA para roles privilegiados en producción; RBAC/ABAC; secretos en OpenBao o equivalente; certificados de dispositivo; logs append-only; ubicación/soporte sujetos a permisos y políticas; cifrado en tránsito y reposo; backups 3-2-1-1-0.

## 12. Definición de DONE por microservicio
Contrato API, tests, migraciones, Docker, `/health/live`, `/health/ready`, métricas/logs, validación/errores, authz, documentación, CI, threat notes y cero mocks/endpoints vacíos usados como producción.

## 13. Versionado
- `v0.1.0`: Foundation + Identity.
- `v0.2.0`: Tenant + Asset + Enrollment/PKI.
- `v0.3.0`: Agent Control + Windows/Linux agent MVP.
- `v0.4.0`: Ticket Service + Help Client + GLPI adapter.
- `v0.5.0`: Tactical/Mesh + software/patching.
- `v0.6.0`: Wazuh + security/compliance/USB.
- `v0.7.0`: Servers + Zabbix + site collector + printers.
- `v0.8.0`: Backup + restore verification.
- `v0.9.0`: Network + Wi-Fi + VPN + NetBox/FreeRADIUS/NetBird.
- `v0.10.0`: Android/iOS MDM + mobile/location.
- `v0.11.0`: Velociraptor/OpenVAS + DFIR/vulnerability.
- `v0.12.0`: Automation + reports + licensing + hardening.
- `v1.0.0`: Enterprise Stable.

Legacy (Windows 7, Lion, Symbian, KaiOS, HarmonyOS específico) usa matriz de capacidades y no retrasa indefinidamente la estabilidad del núcleo moderno.

## 14. Criterios de v1.0.0 Enterprise Stable
Instalación Linux Docker; Windows/macOS Docker compatible para laboratorio; upgrade/rollback; Web/Tauri; identidad/RBAC/MFA; activos/endpoints/servidores/móviles/impresoras; tickets/soporte; políticas/software/parches; Tactical/Mesh/Wazuh/GLPI; backup/restauración; red/Wi-Fi/VPN; auditoría/alertas/reportes/automatización; agentes modernos Windows/Linux/macOS; MDM Android/iOS; CI/CD y pruebas de instalación/upgrade.

## 15. Regla de construcción
`Diseño -> test RED -> implementación GREEN -> integración -> seguridad -> Docker -> documentación -> CI -> DONE -> siguiente servicio`.
