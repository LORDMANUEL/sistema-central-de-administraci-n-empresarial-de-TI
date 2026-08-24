# IT Guardian PKI Service

PKI de dispositivos de IT Guardian. Emite, inventaría, rota y revoca certificados cliente sin recibir nunca la clave privada del endpoint.

## Límites del servicio

PKI posee exclusivamente:

- la BD `guardian_pki`;
- el material del Intermediate CA online;
- metadatos y PEM de certificados públicos emitidos;
- revocaciones y CRL;
- outbox de eventos PKI.

PKI no posee usuarios, empresas, activos, tokens de enrollment, comandos ni telemetría. No escribe bases de Identity, Tenant o Asset.

## Jerarquía CA

```text
Guardian Root CA — RSA 4096
        |
        +-- Device Intermediate CA — RSA 3072
                  |
                  +-- certificados cliente de dispositivos
```

`python -m app.ca_init` es idempotente. Si encuentra material parcial o inconsistente falla; nunca rota o sobrescribe silenciosamente la CA.

El volumen de Root private key solo debe montarse en el job `pki-ca-init`. La API recibe únicamente el volumen online con Intermediate key/cert y Root cert público.

## Claves de dispositivos

La clave privada se genera y permanece en el endpoint. PKI recibe un CSR PKCS#10 y acepta inicialmente:

- RSA >= 2048;
- EC P-256;
- EC P-384.

RSA 1024, curvas no permitidas y CSR con firma inválida se rechazan.

## Perfil del certificado

- lifetime por defecto: 30 días; rango 1–90;
- `BasicConstraints CA=false`;
- `digitalSignature`;
- `keyEncipherment` para RSA;
- EKU `CLIENT_AUTH`;
- SKI/AKI;
- SAN canónico:

```text
spiffe://guardian/tenant/<tenant_id>/asset/<asset_id>/device/<device_id>
```

El CN es solamente una etiqueta; la identidad autorizable usa Guardian IDs/SAN.

## Autorización de emisión

`POST /api/v1/certificates/issue` y `/rotate` requieren un grant Ed25519 firmado por Enrollment Service. El grant expira en <=120 s y enlaza criptográficamente:

- tenant;
- asset;
- device;
- issuance ID;
- SHA-256 del CSR;
- tipo de operación.

No se usa una API key compartida entre Enrollment y PKI.

## Administración

Las operaciones administrativas validan Identity JWT por JWKS y, cuando aplica, consultan Tenant Service:

- `platform_admin`: global;
- `org_admin`: solo su tenant activo;
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

## Idempotencia y rotación

`issuance_id` es único. Un retry idéntico devuelve el mismo certificado. Si el mismo ID llega con CSR/identidad distintos se devuelve conflicto.

La rotación requiere una nueva clave de dispositivo. El reemplazo se persiste primero y el certificado anterior se revoca como `superseded` dentro de la misma transacción.

## Revocación y CRL

La revocación es persistente e idempotente. La CRL se firma con el Intermediate CA y contiene los seriales revocados junto con razón y fecha.

## Eventos

- `pki.certificate.issued`
- `pki.certificate.rotated`
- `pki.certificate.revoked`

Envelope Guardian:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "type": "pki.certificate.issued",
  "aggregate_type": "certificate",
  "aggregate_id": "uuid",
  "occurred_at": "ISO-8601",
  "data": {}
}
```

El outbox usa entrega at-least-once, `Nats-Msg-Id=event_id`, `attempts`, `last_error` y solo establece `published_at` tras ACK.

## Desarrollo

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

Migración:

```bash
PKI_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic upgrade head
PKI_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic downgrade base
PKI_DATABASE_URL=sqlite+pysqlite:///./migration.db alembic upgrade head
```

## Observabilidad

Los logs HTTP registran método, plantilla de ruta, status, duración y `request_id`. No leen ni registran Authorization, CSR o cuerpos de request. Prometheus expone requests, emisiones, rotaciones, revocaciones y resultados del outbox.
