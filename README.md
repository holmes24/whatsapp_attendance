# WhatsApp attendance verification

Production application for receiving attendance photos through Interakt, checking photo date, face, location and reuse signals, and reviewing attendance in the web app. Attendance submissions and audit history are stored in SQL Server; Redis Streams handles queued processing and notifications.

## Included capabilities

- Attendance processing for FS, LS and LSS participants, with direct project-coordinator assignment.
- GPS policy: pass within the configured radius (default 8 km); outside it, compare the registered and photo-derived city/town. Field Supervisors can disable location checks.
- OCR for English, Hindi and Marathi GPS/photo overlays, with English fallback if language data is unavailable.
- Face verification, duplicate-photo and date-edit signals, passive image checks, and manual review.
- Audited status changes, atomic attendance-record/override deletion, manual entries, monthly grid and Excel exports.
- Cost-controlled WhatsApp replies for flagged attendance and late-absence cases.

## Requirements

- SQL Server 2016 or later; SQL Server 2019 or later is recommended. SQL Server 2012 is incompatible.
- Redis 7 or later.
- Docker Engine with Compose, a production HTTPS domain/certificate, and Interakt credentials.

## Deploy

Follow [`PRODUCTION_DEPLOYMENT.md`](PRODUCTION_DEPLOYMENT.md). Configure `backend/.env` from `backend/.env.example` with the deployment SQL Server host/database credentials, Redis URL, Interakt secrets, JWT secret, and allowed frontend origin. The database must already exist; startup creates only the application tables and indexes inside it.

The production Compose file starts the API, workers, frontend, Nginx and Redis. SQL Server is an external service and no database container is started. The deployment team must provide the correct server version, network access, credentials, domain and TLS certificate.

## Local checks

From the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m pip install -r backend/requirements.txt -r backend/requirements-test.txt
python -m pytest backend/tests -q -p no:cacheprovider
```

Build the frontend with `npm ci` and `npm run build` from `frontend/`. Production container builds use `deploy/Dockerfile.backend` and `deploy/Dockerfile.frontend`.
