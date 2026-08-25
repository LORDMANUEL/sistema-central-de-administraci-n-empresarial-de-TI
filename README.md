# IT Guardian

Sistema Central de Administración Empresarial de TI, self-hosted y multiplataforma.

IT Guardian unifica identidad, tenancy, inventario de activos, enrollment seguro, PKI de dispositivos y, progresivamente, control de agentes, telemetría, soporte, seguridad, red, backup, tickets, automatización y auditoría sobre una arquitectura de microservicios.

## Estado

**Versión estable:** `0.4.0`  
**Rama estable:** `main`  
**Core estable:** Identity + Tenant + Asset + PKI + Enrollment  
**Siguiente hito:** `v0.5.0 — Gateway + Audit`

`v0.4.0` fue certificado mediante CI simultáneo de los cinco servicios, instalación desde volúmenes vacíos, E2E de Enrollment/PKI, JetStream, verificación X.509, aislamiento de claves y teardown completo. Un módulo solo se promueve a `main` después de pruebas, migraciones, Docker, Compose e integración E2E reproducible.

## Core disponible en v0.4.0

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
- validación de tenant/site/department por API;
- outbox resiliente + JetStream;
- E2E `Identity -> Tenant -> Asset`.

### PKI Service — :8004

- Root CA RSA-4096 + Device Intermediate RSA-3072;
- Root private key aislada del runtime;
- CSR RSA >=2048 / EC P-256/P-384;
- emisión idempotente por `issuance_id`;
- revocación, CRL y rotación;
- grants Enrollment Ed25519 de corta duración;
- Docker no-root y CA online read-only;
- clean-stack smoke de emisión, revocación, CRL y JetStream.

### Enrollment Service — :8005

- tokens one-time de alta entropía ligados a tenant + asset;
- plaintext entregado una sola vez y solo hash persistido;
- reserva atómica con `device_id` + `issuance_id` estables;
- retry idempotente y replay distinto rechazado;
- CSR generado en endpoint; private key nunca cruza la API;
- grant Ed25519 hacia PKI;
- recuperación ante red/5xx y conflicto de issuance sin duplicar identidad;
- `device.enrolled` y `device.enrollment.failed` mediante outbox;
- inventario administrativo tenant-scoped sin secretos internos;
- clean-stack E2E real `Identity -> Tenant -> Asset -> Enrollment -> PKI -> certificate -> JetStream`.

## Seguridad de claves

- `IDENTITY_SIGNING_KEY` solo pertenece a Identity.
- `ENROLLMENT_SIGNING_KEY` solo pertenece al runtime API de Enrollment; su outbox worker no la recibe.
- La Root CA solo se monta en `pki-ca-init`.
- PKI runtime monta únicamente la Intermediate online en modo read-only.
- Los workers PKI/Enrollment no montan material CA.
- Las private keys de dispositivos se generan y permanecen en el endpoint.

## Arranque Docker

1. Copie `.env.example` a `.env`.
2. Reemplace `POSTGRES_PASSWORD`.
3. Genere **dos semillas Ed25519 diferentes** de 32 bytes:

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode())"
```

Use una en `IDENTITY_SIGNING_KEY` y genere otra distinta para `ENROLLMENT_SIGNING_KEY`.

4. Inicie el stack:

```bash
docker compose up --build -d
```

5. Compruebe los servicios:

```bash
curl http://localhost:8001/health/ready
curl http://localhost:8002/health/ready
curl http://localhost:8003/health/ready
curl http://localhost:8004/health/ready
curl http://localhost:8005/health/ready
```

6. Cree el primer administrador una sola vez:

```bash
curl -X POST http://localhost:8001/api/v1/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","display_name":"Platform Admin","password":"use-a-long-unique-password"}'
```

## Flujo de alta de un endpoint

```text
platform_admin/org_admin
        |
        v
crear tenant/site/department/asset
        |
        v
crear enrollment token (plaintext una sola vez)
        |
        v
endpoint genera private key + CSR
        |
        v
Enrollment reserva device_id + issuance_id
        |
        v
Enrollment firma grant Ed25519
        |
        v
PKI emite certificado cliente
        |
        v
token CONSUMED + device ENROLLED + JetStream
```

## Arquitectura actual

```text
                 ┌───────────────┐
                 │ Identity 8001 │
                 └───────┬───────┘
                         │ JWKS
                ┌────────▼────────┐
                │ Tenant 8002     │
                └────────┬────────┘
                         │
                ┌────────▼────────┐
                │ Asset 8003      │
                └────────┬────────┘
                         │
                ┌────────▼────────┐
                │ Enrollment 8005 │── JWKS/grant ──┐
                └────────┬────────┘                │
                         │                         ▼
                         │                  ┌──────────────┐
                         └─────────────────>│ PKI 8004     │
                                            └──────┬───────┘
                                                   │
                         NATS JetStream <──────────┘

Cada dominio usa su propia base PostgreSQL.
```

En `v0.5.0`, Gateway será el borde HTTP controlado y Audit agregará la bitácora inmutable/tamper-evident; ninguno reemplazará la autorización propia de los servicios.

## Documentación

- `MASTER.md`: arquitectura y reglas maestras.
- `ROADMAP.md`: gates de versión y Definition of Done.
- `CHANGELOG.md`: cambios verificables por release.
- `services/*/README.md`: contratos operativos por microservicio.
- `docs/superpowers/specs/`: especificaciones de arquitectura.
- `docs/superpowers/plans/`: planes TDD ejecutables.

## Licencia

La licencia definitiva se fijará antes del primer release público estable.
