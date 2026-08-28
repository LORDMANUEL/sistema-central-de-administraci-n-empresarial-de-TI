# IT Guardian Web Console Service

BFF y runtime web de IT Guardian v0.8. El navegador utiliza exclusivamente `/console/api/*` con una cookie de sesión opaca `HttpOnly`; los access/refresh tokens de Identity permanecen en memoria del proceso BFF y nunca se entregan a JavaScript.

## Límites de seguridad

- El BFF llama exclusivamente al Gateway.
- `app/api/resources.py` contiene una allowlist fija; no existe proxy catch-all.
- `/api/v1/device/*` no forma parte de la superficie de Web Console.
- La sesión se mantiene en un store acotado en memoria y expira por inactividad.
- En despliegues TLS configure `WEB_CONSOLE_COOKIE_SECURE=true`.
- El fallback SPA rechaza cualquier `/console/api/*` no registrado.

## Runtime

El Dockerfile construye primero React/Vite y luego un runtime Python no-root que sirve la SPA bajo `/console/` y el BFF bajo `/console/api/`.

Health:

- `GET /health/live`
- `GET /health/ready` (verifica Gateway)
