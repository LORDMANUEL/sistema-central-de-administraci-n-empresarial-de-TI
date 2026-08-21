# Identity Service

Identity, authentication and RBAC microservice for IT Guardian.

## Capabilities in v0.1.0

- one-time transactional platform bootstrap;
- Argon2 password hashing;
- access and refresh JWTs with distinct token types and `jti`;
- active/disabled account enforcement;
- current-user endpoint;
- platform-admin user creation, listing and status management;
- stable JSON error contract with request IDs;
- live/readiness health endpoints;
- Prometheus metrics;
- structured HTTP JSON logs;
- Alembic migration;
- PostgreSQL deployment and SQLite test support.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | Database readiness |
| GET | `/metrics` | Prometheus metrics |
| POST | `/api/v1/auth/bootstrap` | Create first platform administrator once |
| POST | `/api/v1/auth/login` | Obtain access/refresh tokens |
| POST | `/api/v1/auth/refresh` | Rotate token pair |
| GET | `/api/v1/users/me` | Current profile |
| POST | `/api/v1/users` | Create user (platform admin) |
| GET | `/api/v1/users` | List users (platform admin) |
| PATCH | `/api/v1/users/{id}/status` | Enable/disable user (platform admin) |

## Local test

```bash
cd services/identity-service
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

On Windows PowerShell activate with `.venv\\Scripts\\Activate.ps1`.

## Database migration

```bash
export IDENTITY_DATABASE_URL='sqlite+pysqlite:///./identity.db'
alembic upgrade head
```

For PostgreSQL use `postgresql+psycopg://user:password@host:5432/database`.

## Run directly

Apply migrations first, then:

```bash
export IDENTITY_JWT_SECRET='replace-with-a-random-secret-of-at-least-32-characters'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Production refuses the development JWT secret.

## Bootstrap example

```bash
curl -X POST http://localhost:8001/api/v1/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","display_name":"Platform Admin","password":"use-a-long-unique-password"}'
```

Bootstrap returns HTTP 409 after completion even if the original administrator row is later removed; the completion state is persistent and transactional.
