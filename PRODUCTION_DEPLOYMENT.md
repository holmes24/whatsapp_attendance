# Production deployment

The application uses SQL Server as its only system of record. Redis carries queued attendance and notification jobs.

## Requirements

- SQL Server 2016 or later; SQL Server 2019 or later is recommended. SQL Server 2012 is incompatible because the app uses `JSON_VALUE` and `ISJSON`.
- Redis 7 or later.
- Docker Engine with Compose.
- A production HTTPS domain and certificate, plus Interakt API and webhook credentials.

The SQL Server database must be created by the database administrator before deployment. The app initializes its own tables and indexes only inside the configured database. It never creates databases or connects to `master`.

## Configure secrets

Copy `backend/.env.example` to `backend/.env` and fill in the approved production values. Keep the file out of Git. Set the SQL host, database, SQL login, password, encryption and certificate validation options supplied by the database team. Also set:

- `JWT_SECRET_KEY` to a long random secret.
- `INTERAKT_WEBHOOK_SECRET` and `INTERAKT_API_KEY` to the Interakt credentials.
- `CORS_ORIGINS` to the production web origin.
- `REDIS_URL` to the Compose Redis service unless the deployment uses an external Redis service.

Use a SQL Server login limited to the application database. Keep TLS encryption enabled and validate the server certificate in production. Never reuse the sample credentials.

## Build and start

From the repository root:

```powershell
docker compose --env-file backend/.env -f deploy/docker-compose.production.yml build
docker compose --env-file backend/.env -f deploy/docker-compose.production.yml up -d
```

The Compose stack starts the API, attendance worker, absence worker, notification worker, frontend, Nginx and Redis. SQL Server is an external service.

Create the initial admin account once the backend is healthy:

```powershell
docker compose --env-file backend/.env -f deploy/docker-compose.production.yml exec backend python scripts/create_admin.py
```

## HTTPS and Interakt

Before starting Nginx, replace `example.com` and the certificate paths in `deploy/nginx.conf` with the real domain and provision its TLS certificate. Point DNS to the server and allow inbound ports 80 and 443.

Set Interakt's webhook URL to:

```text
https://YOUR_DOMAIN/webhook/interakt
```

Nginx redirects HTTP to HTTPS and limits login requests by client IP. The browser login uses individual account credentials; no shared API key is embedded in frontend code.

## Existing roster migration

New participants are assigned directly to a project coordinator. If importing roster data created under the older FS-to-LS hierarchy, back up the SQL database and preview changes from the backend container:

```powershell
docker compose --env-file backend/.env -f deploy/docker-compose.production.yml exec backend python scripts/migrate_reporting_hierarchy.py
```

Review the preview, then run with `--apply` only if the listed assignments are correct.

## Backups and recovery

Back up the SQL Server database using the database team's approved encrypted backup schedule. Store backups separately from the database host and test restoration before launch. Include all `attendance_*` tables, especially roster, submissions, face embeddings, coordinators, webhook events, notifications, admin users, overrides and counters.

## Operations

Check `/api/health` after deployment; it reports Redis and SQL Server health. Run multiple attendance workers with distinct `WORKER_CONSUMER_NAME` values and multiple notification workers with distinct `NOTIFICATION_CONSUMER_NAME` values if scaling is needed.

The still-image liveness checks flag suspicious image quality and face signals; they do not prove real-time presence. Keep manual review enabled for flagged submissions.
