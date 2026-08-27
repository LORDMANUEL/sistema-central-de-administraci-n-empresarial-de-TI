# IT Guardian

Sistema Central de Administración Empresarial de TI, self-hosted y multiplataforma.

IT Guardian está construido como una plataforma de microservicios independientes. La regla del proyecto es simple: **un módulo no se considera terminado hasta tener API/runtime real, tests, migraciones cuando aplique, Docker, Compose, observabilidad, autorización, documentación y prueba de integración con el core anterior**.

## Estado real del proyecto

**Versión estable en `main`: `0.5.0`**  
**Core estable:** Identity + Tenant + Asset + Enrollment + PKI + Gateway + Audit  
**Gate activo:** `v0.6.0 — Agent Control + Command + Telemetry` en PR #8 (draft)  
**Producto final instalable con agente:** todavía NO; falta cerrar v0.6, construir Windows Agent v0.7 y Web Console v0.8.

### Matriz de avance

| Componente | Estado | Rama/release | Observación |
|---|---|---|---|
| Foundation | ✅ TERMINADO | main | estructura y reglas base |
| Identity Service | ✅ TERMINADO | v0.1.0/main | Argon2, JWT Ed25519, JWKS, RBAC |
| Tenant Service | ✅ TERMINADO | v0.2.0/main | empresas, sedes, departamentos, membresías |
| Asset Service | ✅ TERMINADO | v0.3.0/main | inventario canónico y correlación externa |
| Enrollment Service | ✅ TERMINADO | v0.4.0/main | enrollment one-time y device identity |
| PKI Service | ✅ TERMINADO | v0.4.0/main | CA, certificados, revocación, CRL, rotación |
| Gateway Service | ✅ TERMINADO | v0.5.0/main | borde HTTP, allowlist, rate limits, header sanitization |
| Audit Service | ✅ TERMINADO | v0.5.0/main | append-only, hash chain, dedupe, consulta y verificación |
| Agent Control | 🟡 EN DESARROLLO | PR #8 | heartbeat/capabilities/offline; falta cierre operativo completo |
| Command Service | 🟡 EN DESARROLLO | PR #8 | allowlist/idempotencia/adquisición en construcción |
| Telemetry Service | 🟡 EN DESARROLLO | PR #8 | dominio inicial implementado; falta cierre operativo completo |
| Windows Agent Modern | ⬜ PENDIENTE | v0.7.0 | primer binario de endpoint administrable |
| Web Console MVP | ⬜ PENDIENTE | v0.8.0 | administración visual del core |
| Software/Patch/Policy | ⬜ PENDIENTE | v0.9.0 | RMM básico |
| Tickets + Help Client | ⬜ PENDIENTE | v0.10.0 | soporte empresarial |
| Remote Support | ⬜ PENDIENTE | v0.11.0 | control remoto |
| Security/Wazuh/USB | ⬜ PENDIENTE | v0.12.0 | seguridad endpoint |
| Linux/macOS Agents | ⬜ PENDIENTE | v0.13.0 | agentes modernos multiplataforma |
| Servers/Zabbix/Printers | ⬜ PENDIENTE | v0.14.0 | infraestructura |
| Backup | ⬜ PENDIENTE | v0.15.0 | backup/restore verification |
| Network/Wi-Fi/VPN | ⬜ PENDIENTE | v0.16.0 | networking |
| Android/iOS MDM/Location | ⬜ PENDIENTE | v0.17.0 | movilidad |
| DFIR/Vulnerability | ⬜ PENDIENTE | v0.18.0 | respuesta e investigación |
| Automation/Reports/Licensing | ⬜ PENDIENTE | v0.19.0 | automatización empresarial |
| RC integral | ⬜ PENDIENTE | v0.20.0-rc | hardening, upgrade/rollback, instaladores |
| Enterprise Stable | ⬜ PENDIENTE | v1.0.0 | producto estable |

## Camino crítico del Core MVP

```text
Identity
  ↓
Tenant
  ↓
Asset
  ↓
Enrollment + PKI
  ↓
Gateway + Audit
  ↓
Agent Control + Command + Telemetry
  ↓
Windows Agent
  ↓
Web Console
```

No se deben adelantar módulos secundarios mientras esta cadena no sea utilizable de punta a punta.

## Core estable v0.5.0

### Identity Service — :8001

- bootstrap único de `platform_admin`;
- Argon2;
- access/refresh JWT Ed25519;
- JWKS público;
- RBAC base;
- health/readiness, métricas y logs estructurados.

### Tenant Service — :8002

- empresas/tenants;
- membresías y roles por tenant;
- sedes y departamentos jerárquicos;
- autorización tenant-scoped;
- transactional outbox + NATS JetStream;
- BD `guardian_tenant` independiente.

### Asset Service — :8003

- modelo canónico de activos;
- `guardian_asset_id` estable;
- correlación con IDs externos;
- validación tenant/site/department por API;
- outbox resiliente + JetStream;
- E2E `Identity -> Tenant -> Asset`.

### PKI Service — :8004

- Root CA RSA-4096 + Device Intermediate RSA-3072;
- Root private key aislada del runtime;
- CSR RSA >=2048 / EC P-256/P-384;
- emisión idempotente por `issuance_id`;
- revocación, CRL y rotación;
- grants Enrollment Ed25519 de corta duración;
- Docker no-root y CA online read-only.

### Enrollment Service — :8005

- tokens one-time ligados a tenant + asset;
- solo hash persistido del token;
- reserva atómica con `device_id` + `issuance_id` estables;
- retry idempotente y replay distinto rechazado;
- CSR generado en endpoint; private key no cruza la API;
- E2E `Identity -> Tenant -> Asset -> Enrollment -> PKI -> certificate -> JetStream`.

### Audit Service — :8006

- base `guardian_audit` independiente;
- ingesta durable/idempotente desde JetStream;
- registros append-only;
- cadena hash verificable;
- protección contra UPDATE/DELETE desde el rol normal;
- consulta administrativa tenant-scoped;
- secret-safe metadata.

### Gateway Service — :8080

- borde HTTP controlado;
- allowlist estática de rutas/métodos/upstreams;
- validación JWT Ed25519/JWKS;
- bloqueo de headers de identidad/forwarding inyectados por cliente;
- límites de body/header y rate limiting;
- mutaciones sin retry automático;
- auditoría fail-closed antes de mutaciones administrativas;
- sanitización de respuesta upstream.

## Seguridad de claves

- `IDENTITY_SIGNING_KEY` solo pertenece a Identity.
- `ENROLLMENT_SIGNING_KEY` solo pertenece al runtime API de Enrollment.
- la Root CA solo se monta en `pki-ca-init`;
- PKI runtime monta únicamente la Intermediate online en read-only;
- workers PKI/Enrollment no reciben material CA;
- las private keys de dispositivos se generan y permanecen en el endpoint;
- Gateway y Audit no reciben claves privadas de Identity/Enrollment/PKI.

## Instalación estable actual

### Requisitos

- Linux, Windows con Docker Desktop/WSL2 o macOS con Docker Desktop;
- Docker Engine/Compose v2;
- puertos locales libres 8001-8006, 8080 y 8222 según configuración;
- almacenamiento persistente para PostgreSQL, NATS y PKI.

### Arranque

1. Clone el repositorio.
2. Copie `.env.example` a `.env`.
3. Defina una contraseña fuerte en `POSTGRES_PASSWORD`.
4. Genere dos semillas Ed25519 distintas de 32 bytes:

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode())"
```

Use una en `IDENTITY_SIGNING_KEY` y otra en `ENROLLMENT_SIGNING_KEY`.

5. Valide la configuración:

```bash
docker compose config
```

6. Inicie desde stack limpio:

```bash
docker compose up -d --build
```

7. Compruebe estado:

```bash
docker compose ps
curl http://localhost:8001/health/ready
curl http://localhost:8002/health/ready
curl http://localhost:8003/health/ready
curl http://localhost:8004/health/ready
curl http://localhost:8005/health/ready
curl http://localhost:8006/health/ready
curl http://localhost:8080/health/ready
```

8. Cree el primer administrador una sola vez:

```bash
curl -X POST http://localhost:8001/api/v1/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","display_name":"Platform Admin","password":"use-a-long-unique-password"}'
```

### Teardown de laboratorio

```bash
docker compose down -v --remove-orphans
```

> `-v` elimina datos persistentes. No usar en producción salvo que se quiera destruir el entorno.

## Binarios e instaladores

El **servidor actual se distribuye por contenedores Docker**. Los binarios de endpoint todavía no se consideran release porque pertenecen a `v0.7.0 Windows Agent Modern`.

No se publicará un `.exe`, `.msi`, `.pkg`, `.deb`, `.rpm` o paquete móvil como “estable” hasta que tenga:

- build reproducible;
- firma/versionado;
- enrollment real;
- almacenamiento seguro del certificado/clave;
- heartbeat + telemetry;
- command/result;
- upgrade/rollback;
- pruebas E2E contra el mismo SHA del servidor.

## Definition of Done de cada microservicio

- [ ] API/runtime real, sin endpoints falsos de producción.
- [ ] autenticación/autorización explícita.
- [ ] base de datos propia cuando el dominio persista estado.
- [ ] Alembic `upgrade -> downgrade -> upgrade` cuando aplique.
- [ ] `/health/live`, `/health/ready`, Prometheus y `request_id`.
- [ ] Docker no-root.
- [ ] integración en Compose.
- [ ] tests unitarios e integración verdes.
- [ ] transactional outbox/JetStream cuando emita eventos.
- [ ] documentación operativa y notas de seguridad.
- [ ] E2E con los servicios anteriores.
- [ ] clean-stack desde volúmenes vacíos.
- [ ] retry/replay/idempotencia probados cuando aplique.
- [ ] CI verde sobre el mismo SHA candidato.

## Gate para declarar Core MVP funcional

Una instalación limpia debe poder, sin pasos manuales ocultos:

- [ ] levantar todo el servidor;
- [ ] crear/autenticar `platform_admin`;
- [ ] crear empresa, sede, departamento y activo;
- [ ] generar enrollment y certificado de dispositivo;
- [ ] instalar Windows Agent;
- [ ] mostrar el dispositivo ONLINE;
- [ ] recibir CPU/RAM/disco/SO e inventario;
- [ ] ejecutar un comando permitido;
- [ ] recibir resultado idempotente;
- [ ] consultar la operación en Audit;
- [ ] administrar el flujo desde Web Console;
- [ ] actualizar y hacer rollback sin destruir datos.

Hasta que todos estos puntos estén verdes, el proyecto seguirá siendo **core en construcción**, no v1 estable.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos se implementarán mediante una matriz de capacidades separada. No deben bloquear el núcleo moderno ni degradar su seguridad.

## Documentación

- `MASTER.md`: arquitectura y reglas maestras.
- `ROADMAP.md`: gates de versión y Definition of Done.
- `CHANGELOG.md`: cambios verificables por release.
- `services/*/README.md`: contratos operativos por microservicio.
- `docs/superpowers/specs/`: especificaciones de arquitectura.
- `docs/superpowers/plans/`: planes TDD ejecutables.

## Licencia

La licencia definitiva se fijará antes del primer release público estable.
