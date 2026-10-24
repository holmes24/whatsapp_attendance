# Production deployment

## Target architecture

```text
WhatsApp / Interakt
        |
        | HTTPS + Interakt signature
        v
      Nginx
        |
        v
     FastAPI
        |
        | Redis Stream: attendance:jobs
        v
 Unified AI Worker(s)
   |       |       |
   |       |       +--> MongoDB (submission + audit)
   |       |
   |       +----------> Redis Stream: attendance:notifications
   |                              |
   |                              v
   |                    Notification Worker(s)
   |                              |
   +------------------------------+--> Interakt

MongoDB or MSSQL = system of record, selected with DB_BACKEND
Redis = durable work transport / back-pressure / retry queue
Nginx = public TLS termination; ngrok is not used in production
```

## 1. Install dependencies

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Redis locally:

```powershell
docker run -d --name attendance-redis -p 127.0.0.1:6379:6379 redis:8-alpine redis-server --appendonly yes
```

## 2. Configure `.env`

Copy `backend/.env.example` to `backend/.env` and replace every placeholder.
Never commit `.env`.

For production containers, configure the selected database and Redis URLs in
the untracked environment file. SQL Server is configured as an external
service; the MSSQL Compose overlay does not start an extra database container.
If MongoDB is selected, use the optional `mongodb` Compose profile and these
settings:

```text
REDIS_URL=redis://redis:6379/0
DB_BACKEND=mongodb
MONGODB_URL=mongodb://<app-user>:<password>@mongo:27017/attendance_agent?authSource=admin
CORS_ORIGINS=https://attendance.example.com
```

Use a dedicated MongoDB application user rather than the MongoDB root user for the application.

For MSSQL, set `DB_BACKEND=mssql` and provide the production SQL Server host,
database name, encryption settings, and credentials through the deployment
team's secret store. The app only initializes its tables inside the configured
database; it does not create the database or migrate data from MongoDB. Test
schema initialization and any required data migration against a staging copy
before switching production traffic. Do not use the local `.env.mssql` values
as production settings.

Use a currently supported SQL Server release (SQL Server 2019 or newer is
recommended). This backend uses `JSON_VALUE` and `ISJSON`, which require SQL
Server 2016 or newer; SQL Server 2012 is incompatible and out of support.
See Microsoft's [SQL Server JSON documentation](https://learn.microsoft.com/en-us/sql/relational-databases/json/json-data-sql-server)
and [SQL Server 2012 lifecycle](https://learn.microsoft.com/en-us/lifecycle/products/microsoft-sql-server-2012).

When importing roster records created under the older FS-to-LS reporting
hierarchy, back up the selected database and run
`python scripts/migrate_reporting_hierarchy.py` from the backend container to
preview affected records. Apply only after reviewing the preview with
`python scripts/migrate_reporting_hierarchy.py --apply`. New registrations
assign FS, LS, and LSS participants directly to a project coordinator.

## 3. Run the services

Local development:

```powershell
# terminal 1
cd backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# terminal 2
cd backend
.\.venv\Scripts\activate
python -m app.worker

# terminal 3
cd backend
.\.venv\Scripts\activate
python -m app.notification_worker

# terminal 4
cd frontend
npm install
npm run dev
```

Production Docker:

```bash
cd deploy
docker compose --env-file ../backend/.env -f docker-compose.production.yml build
docker compose --env-file ../backend/.env -f docker-compose.production.yml up -d
```

For a MongoDB deployment, add `--profile mongodb` to both commands above. For
MSSQL, add `-f docker-compose.mssql.yml` as shown below; this starts only the
application services and Redis, and connects to the configured SQL Server.

For an MSSQL deployment, the deployment engineer should create
`backend/.env.mssql` from the example with that server's approved connection
settings and include `-f docker-compose.mssql.yml` on both Compose commands.
This overlay selects the MSSQL environment for the API and workers. Keep
credentials out of Git and verify the resolved Compose configuration without
printing its secret values.

The production Compose file sets `ENVIRONMENT=production`; the API checks that
`JWT_SECRET_KEY`, `INTERAKT_WEBHOOK_SECRET`, and `INTERAKT_API_KEY` are set.
Login uses each account's username and password. Nginx limits `/api/auth/login`
to five requests per minute per client IP with a small burst allowance; the
browser does not contain a shared API key.

Before starting Nginx, replace `example.com` and the certificate paths in
`deploy/nginx.conf` with the real domain and provision the matching TLS
certificate. The webhook route is already `/webhook/interakt`; its production
URL is the real HTTPS domain plus that path.

## 4. Production HTTPS

Point DNS `attendance.example.com` to the production server. Open ports 80 and 443 only. Nginx redirects HTTP to HTTPS and proxies `/webhook/interakt` to FastAPI.

Set this URL in Interakt after the domain and TLS certificate are active:

```text
https://attendance.example.com/webhook/interakt
```

There is no ngrok dependency in production.

## 5. Backups

Back up the selected system-of-record database using the database team's
approved schedule. Store backups outside the database host, encrypt them, and
periodically test restoration before production launch.

The backup must include at least:

- `roster`
- `submissions`
- `face_embeddings`
- `webhook_events`
- `notifications`
- `admin_users`
- `coordinators`
- `counters`

## 6. Worker scaling

Run more than one `app.worker` process using the same Redis consumer group and different `WORKER_CONSUMER_NAME` values. Redis Streams will distribute jobs across consumers.

Do the same for `app.notification_worker` with different `NOTIFICATION_CONSUMER_NAME` values.

## 7. Anti-spoofing note

The included liveness check is a passive risk/quality guard. A single WhatsApp still image cannot prove real-time human presence. It deliberately flags suspicious images rather than claiming cryptographic liveness.

For a stronger production control, the next phase should add a trained face anti-spoofing model or a short challenge video/interactive capture flow.
