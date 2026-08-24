# IT Guardian Asset Service

Microservicio canónico de activos de IT Guardian.

## Responsabilidades

- generar y conservar `guardian_asset_id` estable;
- almacenar tenant, sede y departamento como referencias externas/opacas;
- clasificar activos (`computer`, `server`, `mobile`, `printer`, `network`, etc.);
- correlacionar IDs de motores externos sin convertirlos en identidad primaria;
- publicar eventos mediante transactional outbox;
- validar tokens de Identity por JWKS Ed25519.

No escribe la base de datos de Tenant ni comparte la clave privada de Identity.

## API inicial

- `POST /api/v1/assets`
- `GET /api/v1/assets?tenant_id=<uuid>`
- `GET /api/v1/assets/{guardian_asset_id}`
- `POST /api/v1/assets/{guardian_asset_id}/external-identities`
- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

El primer corte administrativo requiere `platform_admin`. El acceso tenant-scoped para operadores se cerrará contra el contrato de autorización inter-servicio de Tenant antes de promover `v0.3.0`.

## Eventos

- `asset.created`
- `asset.external_identity.linked`

Los eventos se guardan en `outbox_events` en la misma transacción del cambio de dominio. El worker publica en NATS JetStream con `Nats-Msg-Id=event_id` y solo marca `published_at` tras recibir ACK.

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

## Estado

Este servicio está en `0.3.0-dev.1`. No se considera DONE hasta que CI, build Docker, migración round-trip, Compose y el gate `Identity -> Tenant -> Asset -> NATS` estén verdes.
