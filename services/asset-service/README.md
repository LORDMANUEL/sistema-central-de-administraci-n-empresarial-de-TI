# IT Guardian Asset Service

Microservicio canónico de activos de IT Guardian.

## Responsabilidades

- generar y conservar `guardian_asset_id` estable;
- almacenar tenant, sede y departamento como referencias externas/opacas;
- clasificar activos (`computer`, `server`, `mobile`, `printer`, `network`, etc.);
- correlacionar IDs de motores externos sin convertirlos en identidad primaria;
- autorizar operaciones mediante Identity + Tenant Service sin compartir bases de datos;
- validar sede y departamento en Tenant antes de persistir referencias;
- publicar eventos mediante transactional outbox resistente a caídas de NATS;
- validar tokens de Identity por JWKS Ed25519.

Asset Service no escribe la base de Tenant y nunca recibe la clave privada de Identity.

## API

- `POST /api/v1/assets`
- `GET /api/v1/assets?tenant_id=<uuid>`
- `GET /api/v1/assets/{guardian_asset_id}`
- `POST /api/v1/assets/{guardian_asset_id}/external-identities`
- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

## Autorización por empresa

El bearer token se valida criptográficamente contra el JWKS público de Identity. Para usuarios no globales, Asset consulta el contrato `/api/v1/tenants/{tenant_id}/access` de Tenant Service.

- `platform_admin`: lectura y escritura global, sin depender de una membresía por tenant.
- `org_admin`: lectura y escritura dentro de sus tenants activos.
- demás membresías activas: lectura dentro de su tenant.
- usuario sin membresía/inactivo: acceso denegado.
- tenant suspendido: acceso tenant-scoped denegado.

Antes de crear un activo con `site_id` o `department_id`, Asset consulta `/api/v1/tenants/{tenant_id}/references/validate`; una referencia inexistente, inactiva o perteneciente a otra empresa se rechaza antes del `flush/commit`.

## Correlación externa

`guardian_asset_id` es la identidad primaria y estable. Los identificadores de terceros se almacenan como correlaciones únicas, por ejemplo:

- Tactical RMM / MeshCentral;
- Wazuh;
- GLPI;
- Zabbix;
- NetBox;
- NetBird;
- MDM;
- Velociraptor.

El mismo `(provider, external_id)` no puede apuntar a dos activos Guardian.

## Eventos y recuperación

Eventos actuales:

- `asset.created`;
- `asset.external_identity.linked`.

Los eventos se escriben en `outbox_events` en la misma transacción del cambio de dominio. El worker usa envelope común:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "type": "asset.created",
  "aggregate_type": "asset",
  "aggregate_id": "guardian-asset-id",
  "occurred_at": "ISO-8601",
  "data": {}
}
```

Entrega:

1. selecciona únicamente eventos sin `published_at`;
2. cada evento se intenta como máximo una vez por ciclo de polling;
3. incrementa `attempts` antes del envío;
4. si NATS falla, conserva el evento y registra `last_error`;
5. publica con `Nats-Msg-Id=event_id` para deduplicación JetStream;
6. solo establece `published_at` tras recibir ACK;
7. el siguiente ciclo puede reintentar de forma segura.

La semántica es **at-least-once**, por lo que los consumidores deben tratar `event_id` de forma idempotente.

## Desarrollo

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

Migraciones:

```bash
ASSET_DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic upgrade head
ASSET_DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic downgrade base
ASSET_DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic upgrade head
```

Stack de integración:

```bash
POSTGRES_PASSWORD='<password>' \
IDENTITY_SIGNING_KEY='<ed25519-seed-base64url>' \
docker compose up -d --build
```

El gate CI ejecuta además `tests/e2e/core_identity_tenant_asset.py`, crea desde cero Identity → Tenant → Site/Department → Asset y comprueba que `guardian.asset.created` llegue a NATS JetStream.

## Definition of Done v0.3.0

No se promueve la versión hasta que, sobre el mismo SHA candidato, estén verdes: suite Python, compile, Alembic `upgrade -> downgrade -> upgrade`, Docker build, Compose config y `core-e2e` de instalación limpia con JetStream.
