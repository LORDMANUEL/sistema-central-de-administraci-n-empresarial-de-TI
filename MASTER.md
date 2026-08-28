# IT Guardian — MASTER

**Producto:** Sistema Central de Administración Empresarial de TI  
**Nombre:** IT Guardian  
**Repositorio:** `LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI`  
**Arquitectura:** microservicios independientes + agentes por plataforma  
**Release del core:** `v0.7.0` certificado  
**Gate activo:** `v0.8.0 Web Console MVP`  
**Objetivo:** `v1.0.0 Enterprise Stable`

## 1. Propósito

IT Guardian es una plataforma self-hosted para administrar identidades, sedes, activos, endpoints, servidores, móviles, impresoras, red, seguridad, soporte, backup y automatización. Cada dominio se construye y versiona de forma independiente; un servicio cerrado no se reabre salvo bug demostrado o contrato nuevo explícitamente versionado.

Cada activo recibe un `guardian_asset_id` estable y puede correlacionarse con identificadores externos de motores especializados. Los motores OSS son adaptadores/backends reemplazables, no la UX final del producto.

## 2. Principios no negociables

1. Base de datos por dominio; no hay escritura cruzada entre microservicios.
2. TDD para comportamiento nuevo y gates E2E antes de DONE.
3. Zero-trust entre dominios y entre endpoint/servidor.
4. Secret safety por allowlist; tokens/private keys no entran a logs/eventos/audit.
5. Mínimo privilegio y runtime non-root cuando aplique.
6. Private keys de endpoints se generan y permanecen en el dispositivo.
7. Operación offline durable para endpoints.
8. No existe shell remoto arbitrario como primitive del core.
9. Compatibilidad explícita por plataforma; no se simula paridad.
10. SemVer, changelog y evidencia de CI sobre el candidato promovido.

## 3. Arquitectura certificada hasta v0.7

```text
                            ADMIN PLANE
Web Console v0.8 (siguiente) / API clients
                    |
                    v
              Gateway :8080
                    |
     +--------------+---------------+----------------+
     |              |               |                |
 Identity :8001  Tenant :8002   Asset :8003    Audit :8006
                                  |
                            Enrollment :8005
                                  |
                              PKI :8004

                           DEVICE PLANE
Windows Agent Modern 0.7
          |
          | HTTPS + mTLS / X.509 SPIFFE
          v
     Device Edge :8443
          |
          +---- Agent Control :8007
          +---- Command       :8008
          +---- Telemetry     :8009

Domains <---- NATS JetStream ----> Workers ----> Audit
Domains ----> PostgreSQL independiente por dominio
```

El Gateway no expone las rutas de dispositivo. Device Edge termina mTLS, valida CRL, deriva el principal desde el certificado y solo proxifica la allowlist device-facing.

## 4. Núcleo implementado

1. `identity-service`: usuarios, credenciales, JWT Ed25519/JWKS y RBAC.
2. `tenant-service`: organizaciones, sedes, departamentos y membresías.
3. `asset-service`: modelo canónico de activos y correlación externa.
4. `enrollment-service`: tokens one-time, reserva e identidad de dispositivo.
5. `pki-service`: CA, emisión, rotación, revocación y CRL.
6. `gateway-service`: borde administrativo HTTP allowlisted.
7. `audit-service`: auditoría append-only/tamper-evident.
8. `agent-control-service`: heartbeat, capabilities y online/offline.
9. `command-service`: jobs tipados, leases y resultados idempotentes.
10. `telemetry-service`: ingestión allowlisted, dedupe y latest.
11. `device-edge-service`: borde mTLS del endpoint, X.509/SPIFFE y CRL.
12. `windows-agent`: servicio de endpoint, DPAPI, telemetry, commands, spool y updater firmado.

## 5. Windows Agent v0.7

Target moderno: Windows 10/11 y Windows Server modernos. La evidencia automatizada ejecuta x64 en runner Windows y compile-gatea arm64; la matriz física por edición/hardware se documenta aparte.

Propiedades certificadas:

- servicio no interactivo `ITGuardianAgent` bajo LocalService;
- MSI x64 Auto + delayed-auto, detenido hasta enrollment;
- ECDSA P-256 + CSR local;
- private key DPAPI LocalMachine;
- mTLS obligatorio hacia Device Edge;
- CPU/RAM/discos + platform version;
- comandos `inventory.refresh`, `device.reboot`, `service.restart`;
- WinAPI/SCM directo, sin shell remoto;
- spool 64 MiB/10k, prioridad de resultados y retry/backoff;
- updater con manifest Ed25519, HTTPS, SHA-256, anti-downgrade y rollback por health marker.

## 6. Seguridad v0.7

- Root PKI está aislada del runtime.
- Enrollment signer no se comparte con PKI/workers.
- Device Edge no monta su CA privada TLS de servidor.
- El principal de dispositivo nunca se acepta desde headers controlados por cliente.
- CRL inválida/expirada degrada readiness/falla cerrado para acceso de dispositivo.
- Windows Agent nunca persiste enrollment token.
- DPAPI protege la private key en reposo.
- El update acepta solo feed/clave pública pinneados en config; no existe URL arbitraria por comando.
- `shell.exec`, `cmd.exe` y PowerShell remoto no forman parte del Command Service/agent executor.

## 7. Eventos canónicos implementados

Incluyen `identity.user.*`, `tenant.*`, `asset.*`, `enrollment.token.*`, `device.enrolled`, `device.enrollment.failed`, `pki.certificate.*`, `device.online`, `device.offline`, `device.capabilities.changed`, lifecycle `command.*` y `telemetry.batch.accepted`.

## 8. Plataformas objetivo

### Servidor
- Linux x86_64/arm64 con Docker/Compose recomendado para producción.
- Windows Docker Desktop/WSL2 y macOS Docker Desktop para instalaciones compatibles/laboratorio.

### Consola
- Web React + TypeScript en v0.8.
- Desktop Tauri reutilizando la capa visual en gate posterior cuando el Web MVP esté estable.

### Agentes
- Windows 10/11 moderno: v0.7 Modern.
- Windows 7/8/8.1: Legacy, capacidades reducidas, gate separado.
- Linux/macOS modernos: v0.13.
- macOS Lion–10.12: legacy separado.
- Android/iOS/Huawei/KaiOS/Symbian: gates de movilidad/legacy posteriores.

## 9. Inventario de dominios posteriores

### Endpoint operations
`software-service`, `patch-service`, `policy-service`, `remote-support-service`, `usb-service`, `backup-service`.

### Seguridad
`security-service`, `vulnerability-service`, `forensic-service`, adaptador de secrets.

### Red e infraestructura
`network-service`, `wifi-service`, `vpn-service`, `printer-service`, `site-collector-service`, `server-service`.

### Movilidad
`mobile-service`, Android/Apple/Huawei MDM y `location-service`.

### ITSM/negocio TI
`ticket-service`, `notification-service`, `license-service`, `report-service`, `automation-service`, `integration-service`.

## 10. UX objetivo

Overview; Assets; Operations; Security; Network; Service Desk; Identity; Automation; Reports; Audit; Integrations; Settings. La Web Console v0.8 debe consumir Gateway, respetar RBAC backend y no leer bases de datos directamente.

## 11. Políticas offline

El endpoint mantiene estado/identidad/spool local. Una caída de red no reejecuta un comando ya ejecutado solo porque falló el upload del resultado. Los resultados terminales tienen prioridad sobre telemetry en presión de capacidad.

## 12. Definition of DONE

Contrato/runtime real, auth explícita, persistencia/migraciones cuando aplique, observabilidad, Docker/installer, tests, secret isolation, E2E, clean-stack, idempotencia/replay, documentación y CI verde sobre el candidato.

## 13. Versionado vigente

- `v0.1.0`: Foundation + Identity — DONE.
- `v0.2.0`: Tenant — DONE.
- `v0.3.0`: Asset — DONE.
- `v0.4.0`: Enrollment + PKI — DONE.
- `v0.5.0`: Gateway + Audit — DONE.
- `v0.6.0`: Agent Control + Command + Telemetry — DONE.
- `v0.7.0`: Device Edge + Windows Agent Modern — CERTIFICADO.
- `v0.8.0`: Web Console MVP — SIGUIENTE.
- `v0.9.0`: Software + Patch + Policy.
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

## 14. Gate activo: v0.8 Web Console

No se adelantan microservicios secundarios hasta poder operar visualmente el core ya certificado: login, tenancy, assets/devices, estado, telemetry, comandos, Audit y enrollment.

## 15. Regla de construcción

`Diseño -> test RED -> implementación GREEN -> integración -> seguridad -> packaging -> E2E -> documentación -> CI -> DONE -> siguiente gate`.
