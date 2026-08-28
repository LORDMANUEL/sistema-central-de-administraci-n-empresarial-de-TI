# IT Guardian Web Console Service

BFF y runtime web de IT Guardian `v0.8.0`. El navegador usa exclusivamente `/console/api/*` con una cookie de sesión opaca `HttpOnly`. Los access/refresh tokens de Identity permanecen del lado servidor y nunca se entregan a JavaScript.

## Límites de seguridad

- El BFF llama exclusivamente al Gateway administrativo.
- `app/api/resources.py` mantiene una allowlist fija; no existe proxy catch-all.
- `/api/v1/device/*` no forma parte de la superficie Web Console.
- Las sesiones de producción se guardan en Valkey/Redis mediante `WEB_CONSOLE_SESSION_REDIS_URL`; en `GUARDIAN_ENV=production` el arranque falla si el store no está disponible/configurado.
- Compose mantiene Valkey en la red interna y no publica su puerto al host.
- Cookie `HttpOnly` + `SameSite=Strict`; `Secure` debe mantenerse habilitado detrás de HTTPS en producción.
- Las mutaciones requieren CSRF.
- CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` y `Permissions-Policy` se aplican en el BFF.
- Las respuestas `/console/api/*` usan `Cache-Control: no-store`.
- El frontend no persiste access/refresh tokens ni scope de tenant/sede en `localStorage`/`sessionStorage`.
- El fallback SPA rechaza cualquier `/console/api/*` no registrado.

## Runtime

El Dockerfile construye React/Vite y produce un runtime Python non-root. La SPA se sirve bajo `/console/` y el BFF bajo `/console/api/`.

Health:

- `GET /health/live`
- `GET /health/ready` — valida el store de sesión y Gateway.

## Certificación v0.8

El workflow `web-console-ci.yml` cubre tests frontend/BFF, TypeScript/Vite, boundary scans, imagen non-root, Compose, Valkey interno y clean-stack Chromium. El E2E crea un tenant/sede/activo real, enrola un endpoint, usa certificado mTLS para heartbeat/telemetry, crea un comando desde el navegador, lo consume por Device Edge y exige resultado `SUCCEEDED`, Audit y logout.

Para producción publique la consola detrás de TLS/reverse proxy y mantenga `WEB_CONSOLE_COOKIE_SECURE=true`. El valor `false` solo se usa en el E2E HTTP de localhost.
