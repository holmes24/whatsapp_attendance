# Attendance AI Backend

The backend is the FastAPI ingress/admin API plus Redis Streams workers.

See the repository root `README.md` for the complete fresh Windows setup, architecture, fraud-test checklist and production deployment instructions.

## Processes

- `uvicorn app.main:app` — FastAPI webhook/auth/admin API
- `python -m app.worker` — unified attendance AI worker
- `python -m app.notification_worker` — durable WhatsApp/admin notification worker

The webhook only validates the signature, persists the idempotency event and enqueues a Redis Stream job. OCR, face verification, geofence, duplicate/reuse detection, passive liveness and attendance classification run in the worker.

## Configuration

Copy `.env.example` to `.env`. Secrets are never committed. Tesseract is configured with `TESSERACT_CMD`; no Windows path is hardcoded.

### Optional SQL Server backend

MongoDB remains the default: omit `DB_BACKEND` or leave it set to `mongodb`.
For SQL Server, set `DB_BACKEND=mssql` and supply the host, database,
authentication, and encryption settings from the deployment environment. See
the root `PRODUCTION_DEPLOYMENT.md` for the production configuration.

For local SQL Server testing, select MSSQL only in the local backend process:

```powershell
Set-Location backend
$env:DB_BACKEND = "mssql"
$env:MSSQL_SERVER = "localhost"
$env:MSSQL_DATABASE = "attendance_agent_local"
$env:MSSQL_TRUSTED_CONNECTION = "true"
$env:MSSQL_ENCRYPT = "false"
$env:MSSQL_TRUST_SERVER_CERTIFICATE = "true"
uvicorn app.main:app --reload
```

The defaults target `localhost`, ODBC Driver 18, and Windows integrated
authentication; no SQL username or password is needed. Adjust `MSSQL_SERVER`,
`MSSQL_DATABASE`, or the ODBC encryption options for another local installation.
Keep the shared `backend/.env` unchanged if Docker Compose loads it; do not set
`DB_BACKEND=mssql` there for local-only testing. Give each local API/worker
process the same MSSQL environment, and point `REDIS_URL` at the Redis instance
used for that local test.
For environments that require SQL authentication instead, set
`MSSQL_TRUSTED_CONNECTION=false` and supply `MSSQL_USERNAME` /
`MSSQL_PASSWORD` through an untracked secret store or process environment.

### SQL Server from Docker on Windows

The Linux containers use SQL authentication to reach a Windows-hosted SQL
Server. Keep credentials in the ignored `backend/.env.mssql` file (start from
`backend/mssql.env.example`), and use `host.docker.internal` for the SQL Server
host. The Docker backend image installs Microsoft ODBC Driver 18.

Add `-f deploy/docker-compose.mssql.yml` to the Compose files when starting this
stack. This override applies only to the backend and workers; Redis, MongoDB,
Nginx, and frontend configuration are unchanged. The configured database must
already exist. Startup creates/updates only the app's tables and indexes in
that database; it does not create/drop databases or migrate MongoDB data.

At startup, the API and standalone workers initialize the SQL schema only in
the configured database. The database itself must already exist; the app never
connects to `master` or creates/deletes databases. SQL Server stores each
logical collection as JSON rows with SQL-enforced computed-column indexes for
the application's unique and lookup fields. This backend does not migrate or
mirror MongoDB data. Regex-based search currently evaluates the matching
collection in the application, so production-scale datasets should be measured
and indexed/query-optimized before rollout.

## Data safety

The selected database is the system of record; switching backends does not
copy data. Every image submission is retained for audit, including additional
submissions made after a valid attendance result. Fraud evidence stores image
fingerprints and references to previous submissions rather than exposing face
embeddings to the frontend.

## Tests

Install the test dependencies in a development environment, then run the
backend suite from the `backend` directory:

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -q -p no:cacheprovider
```

The MSSQL tests in `tests/test_mssql_backend.py` validate SQL query and
connection configuration logic without connecting to a live SQL Server. A
separate staging database is still required to verify a real deployment.
