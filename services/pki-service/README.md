# IT Guardian PKI Service

Microservicio de PKI para identidades criptográficas de dispositivos de IT Guardian.

## Responsabilidad

PKI posee exclusivamente `guardian_pki`, el Intermediate CA online, certificados públicos emitidos, revocaciones/CRL y el outbox de eventos PKI. No escribe las bases de Identity, Tenant o Asset y nunca recibe la clave privada del endpoint.

## Jerarquía

```text
Guardian Root CA — RSA 4096
        |
        +-- Device Intermediate CA — RSA 3072
                  |
                  +-- certificados cliente
```

`python -m app.ca_init` inicializa la jerarquía de forma idempotente. Material parcial o inconsistente provoca un fallo seguro; no se sobrescriben claves existentes.

El volumen con la Root private key se monta únicamente en `pki-ca-init`. `pki-service` recibe solo el volumen online en modo read-only y `pki-outbox-worker` no necesita material CA.

## Claves de dispositivo

La clave privada se genera en el endpoint. PKI recibe únicamente un CSR PKCS#10. Perfil inicial:

- RSA >= 2048;
- EC P-256;
- EC P-384.

RSA 1024, curvas no admitidas o CSR con firma inválida se rechazan antes de persistir.

## Certificado Guardian

- 30 días por defecto, configurable 1–90;
- `BasicConstraints CA=false`;
- EKU `CLIENT_AUTH`;
- SKI/AKI;
- `digitalSignature` y `keyEncipherment` para RSA;
- SAN canónico `spiffe://guardian/tenant/<tenant>/asset/<asset>/device/<device>`.

El CN es solo una etiqueta; la identidad autorizable se deriva de Guardian IDs/SAN.

## Emisión y rotación

`POST /api/v1/certificates/issue` y `/rotate` exigen un grant Ed25519 de Enrollment Service con duración máxima de 120 segundos. El grant enlaza tenant, asset, device, `issuance_id` y SHA-256 del CSR.

`issuance_id` es idempotente: un retry idéntico devuelve el mismo certificado; datos distintos producen conflicto. La rotación exige una nueva clave, crea el reemplazo y revoca el anterior como `superseded` en la misma transacción.

## Administración

Las operaciones administrativas verifican Identity JWT por JWKS y Tenant Service:

- `platform_admin`: global;
- `org_admin`: su tenant activo;
- otros roles/no miembros: denegados;
- tenant suspendido: denegado.

## API

Público:
- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`
- `GET /api/v1/ca/chain`
- `GET /api/v1/ca/crl`

Enrollment:
- `POST /api/v1/certificates/issue`
- `POST /api/v1/certificates/rotate`

Administración:
- `GET /api/v1/certificates?tenant_id=<id>`
- `GET /api/v1/certificates/{certificate_id}`
- `POST /api/v1/certificates/{certificate_id}/revoke`

## Revocación y eventos

La revocación es persistente e idempotente. La CRL se firma con el Intermediate CA.

Eventos:
- `pki.certificate.issued`
- `pki.certificate.rotated`
- `pki.certificate.revoked`

El outbox usa envelope Guardian `schema_version=1`, entrega at-least-once, `Nats-Msg-Id=event_id`, `attempts`, `last_error` y marca `published_at` solo tras ACK.

## Desarrollo y verificación

```bash
python -m pip install -e '.[test]'
python -m pytest -q
PKI_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic upgrade head
PKI_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic downgrade base
PKI_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic upgrade head
```

Los logs HTTP incluyen método, ruta, status, duración y `request_id`; nunca leen Authorization ni cuerpos/CSR. Prometheus expone HTTP, emisión, rotación, revocación y resultados del outbox.
