# IT Guardian Enrollment Service

Microservicio de alta segura de endpoints de IT Guardian.

## Responsabilidades

- crear tokens de enrollment de alta entropía ligados a un tenant y activo existente;
- almacenar únicamente SHA-256 del token y un hint no secreto;
- reservar/consumir tokens one-time con retry idempotente y rechazo de replay;
- generar `device_id` e `issuance_id` estables antes de cruzar la red;
- validar CSR sin recibir nunca la private key del endpoint;
- firmar grants Ed25519 de corta duración para PKI;
- orquestar emisión idempotente con PKI;
- persistir estado y metadatos públicos del certificado;
- publicar eventos mediante transactional outbox.

Enrollment no escribe las bases de Identity, Tenant, Asset o PKI.

## Flujo

```text
Admin Identity JWT
      |
      +--> Tenant authorization
      +--> Asset validation
      |
      v
Enrollment token one-time
      |
      v
Endpoint private key + CSR local
      |
      v
RESERVED device_id + issuance_id
      |
      v
Ed25519 grant <= 120 s
      |
      v
PKI certificate
      |
      v
CONSUMED + ENROLLED + device.enrolled
```

## Token

El plaintext tiene formato `gdt_<random>` y usa al menos 256 bits de aleatoriedad. Se devuelve únicamente en el `POST` de creación y nunca se persiste. La BD conserva solo hash SHA-256 y un hint corto.

Estados lógicos:

- `active`;
- `reserved`;
- `consumed`;
- `revoked`;
- `expired`.

Un retry idéntico de un token RESERVED/CONSUMED recupera la misma identidad. Un request distinto con ese token se rechaza como replay.

## Recuperación

- red/PKI 5xx: conserva PENDING + RESERVED + mismos `device_id`/`issuance_id`;
- `pki_issuance_conflict`: conserva los mismos IDs, nunca crea otra identidad para ocultar el conflicto;
- rechazo PKI corregible antes de certificado: marca FAILED, emite `device.enrollment.failed` y libera la reserva;
- retry posterior corregido obtiene nuevos IDs solo si no existe certificado.

## Autorización administrativa

- `platform_admin`: global;
- `org_admin`: tenant activo administrado;
- otros roles/no miembro/suspendido: denegado.

La autorización se resuelve con Identity JWKS + Tenant Service. La validación del activo se realiza por Asset Service usando el bearer del administrador.

## API

Público/endpoint:

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`
- `GET /.well-known/jwks.json`
- `POST /api/v1/enrollments`

Administración:

- `POST /api/v1/enrollment-tokens`
- `GET /api/v1/enrollment-tokens?tenant_id=...`
- `POST /api/v1/enrollment-tokens/{token_id}/revoke`
- `GET /api/v1/enrollments?tenant_id=...`
- `GET /api/v1/enrollments/{device_id}`

Las respuestas administrativas de enrollment no exponen token/hash, CSR, request fingerprint ni PEM almacenados.

## Signer

Enrollment usa un seed Ed25519 de 32 bytes codificado base64url:

```text
ENROLLMENT_SIGNING_KEY=<base64url-32-byte-seed>
```

El API runtime recibe esa variable. El outbox worker no la necesita y no debe recibirla. PKI recibe únicamente `/.well-known/jwks.json` y grants firmados.

## Eventos

- `enrollment.token.created`
- `enrollment.token.revoked`
- `device.enrolled`
- `device.enrollment.failed`

El envelope usa `schema_version=1`. Los eventos nunca incluyen token plaintext/hash, bearer, CSR ni signing seed.

## Desarrollo

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

Migraciones:

```bash
ENROLLMENT_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic upgrade head
ENROLLMENT_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic downgrade base
ENROLLMENT_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic upgrade head
```

## Observabilidad

Los logs HTTP contienen únicamente método, plantilla de ruta, status, duración y `request_id`. No inspeccionan Authorization ni cuerpos de request. Prometheus expone requests, lifecycle de tokens, enrollment, PKI y outbox.
