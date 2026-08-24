# IT Guardian

Sistema Central de Administración Empresarial de TI, self-hosted y multiplataforma.

IT Guardian unifica endpoints, servidores, móviles, impresoras, red, seguridad, soporte remoto, backups, VPN, Wi-Fi, políticas, inventario, tickets, auditoría y automatización sobre una arquitectura de microservicios.

## Estado

**Rama activa:** `feature/v0.1.0-foundation`  
**Versión:** `0.1.0-dev.2`  
**Primer servicio:** Identity Service

La rama `main` se conserva como línea estable. Los módulos se terminan, prueban y documentan antes de promoverse.

## Documentación principal

- `MASTER.md`: visión, módulos, submódulos, integraciones, plataformas, versiones y Definition of Done.
- `docs/superpowers/specs/2026-08-21-it-guardian-platform-design.md`: decisión arquitectónica.
- `docs/superpowers/plans/2026-08-21-v0.1.0-foundation-identity.md`: plan ejecutable de v0.1.0.
- `services/identity-service/README.md`: uso del primer microservicio.

## v0.1.0 Foundation

Incluye el primer corte de Identity Service:

- bootstrap único y transaccional del `platform_admin`;
- Argon2;
- JWT Ed25519/EdDSA access/refresh con `kid`, issuer y audience;
- JWKS público para validación inter-servicio sin compartir clave privada;
- RBAC inicial;
- alta/listado/activación de usuarios;
- errores normalizados con `request_id`;
- health/readiness;
- métricas Prometheus;
- logs HTTP JSON;
- migración Alembic;
- PostgreSQL + Docker Compose;
- CI con tests y smoke test de migraciones.

## Arranque Docker

1. Copie `.env.example` a `.env`.
2. Reemplace `POSTGRES_PASSWORD` y genere una semilla Ed25519 privada de 32 bytes:

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=') .decode())"
```

Guarde el resultado en `IDENTITY_SIGNING_KEY`. La clave privada solo pertenece a Identity; los demás microservicios validarán tokens mediante `/.well-known/jwks.json`.
3. Ejecute:

```bash
docker compose up --build -d
```

4. Compruebe:

```bash
curl http://localhost:8001/health/ready
```

5. Cree el primer administrador una sola vez:

```bash
curl -X POST http://localhost:8001/api/v1/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","display_name":"Platform Admin","password":"use-a-long-unique-password"}'
```

## Arquitectura

```text
Web React/TypeScript + Tauri
          │
      API Gateway
          │
 ┌────────┼─────────┐
Identity Assets  Tickets ...
          │
   NATS JetStream
          │
Integraciones y agentes
```

El servidor de producción recomendado es Linux + Docker. Windows y macOS podrán ejecutar el stack mediante Docker para laboratorio, edge pequeño y desarrollo.

## Licencia

La licencia definitiva se fijará antes del primer release público estable.
