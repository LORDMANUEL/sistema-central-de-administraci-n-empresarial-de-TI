# IT Guardian Gateway Service

Gateway HTTP norte de IT Guardian. Expone únicamente rutas registradas de forma explícita y conserva la autenticación/autorización propia de cada microservicio downstream.

## Límites del servicio

Gateway es stateless en v0.5.0. No posee base de datos ni claves privadas de Identity, Enrollment o PKI.

Recibe únicamente:

- URLs internas fijas de Identity, Tenant, Asset, Enrollment, PKI y Audit;
- JWKS público de Identity;
- NATS para auditoría de borde;
- configuración de límites/rate-limit.

## Principios de seguridad

- No existe proxy catch-all ni upstream controlado por el cliente.
- `X-Guardian-*`, `Forwarded`, `X-Forwarded-*`, `Host` y headers hop-by-hop del caller se eliminan.
- `X-Request-ID` se valida/genera en Gateway y se propaga.
- Las rutas `identity` validan JWT Ed25519/JWKS en Gateway y el mismo bearer se reenvía al servicio, que vuelve a validar su propia autorización.
- `POST/PATCH/PUT/DELETE` no tienen retry automático.
- `GET/HEAD` tienen como máximo un retry y únicamente ante `ConnectError` antes de recibir respuesta.
- El límite de body se aplica antes de llamar al upstream.
- Las mutaciones privilegiadas con `audit_intent_required=true` requieren ACK de JetStream para `gateway.request.accepted` antes de ejecutar el upstream.
- El fallo posterior de `gateway.request.completed` nunca repite una mutación ya realizada.

## Rutas

La fuente de verdad es `app/routes.py`. Cada `RoutePolicy` declara:

- `route_id` estable;
- método exacto;
- plantilla de path;
- URL/path upstream fija;
- `auth_mode`;
- mutation/audit intent;
- body limit;
- timeout;
- bucket de rate-limit.

Las rutas internal-only, incluyendo Tenant `/access`, JWKS inter-servicio y emisión directa PKI, no se registran como northbound.

## Pipeline

```text
request
  -> route policy
  -> request-id
  -> header/body limits
  -> edge Identity validation (cuando aplica)
  -> rate-limit
  -> audit intent fail-closed (cuando aplica)
  -> upstream fijo
  -> response header sanitization
  -> metrics/log secret-safe
```

## Observabilidad

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

Los logs registran request ID, route ID, método, plantilla normalizada, status y duración. No reciben Authorization ni body como argumentos y no imprimen payloads arbitrarios.

## Docker

La imagen corre con usuario no-root `guardian` y escucha internamente en `8000`. Compose publica el Gateway en loopback `127.0.0.1:${GATEWAY_PORT:-8080}` hasta que un reverse proxy/TLS externo sea configurado.

## Desarrollo

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

## Definition of Done v0.5.0

Gateway no se considera terminado hasta que sobre un mismo SHA candidato pasen:

1. suite Python/compile;
2. Docker build y UID no-root;
3. Compose config;
4. clean-stack completo por puerto 8080;
5. bloqueo de rutas internal-only;
6. sanitización de headers spoofables;
7. 413 y 429 antes del upstream;
8. audit-intent fail-closed sin mutación;
9. `accepted/completed` ingeridos por Audit y hash-chain válida;
10. secret scan y teardown;
11. CIs existentes de Identity/Tenant/Asset/Enrollment/PKI/Audit verdes.
