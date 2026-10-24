# Attendance AI — Production Architecture

## Architecture

```text
WhatsApp / Interakt
       |
       v
Nginx + HTTPS
       |
       v
FastAPI (webhook/auth/admin APIs)
       |
       | Redis Streams
       v
Unified AI Worker(s)
  | OCR | Face | Geofence | Duplicate | Liveness
  v
MongoDB (system of record + audit)
       |
       v
Notification Stream
       |
       v
Notification Worker(s)
       |
       v
WhatsApp / Admin
```

FastAPI never performs the expensive attendance AI pipeline synchronously. Redis Streams provides buffering, consumer-group distribution, retry and dead-letter transport. MongoDB stores every submission, including suspicious additional submissions for audit.

## Attendance states

- **P** — Present
- **L** — Present but late
- **F** — Flagged and awaiting admin review
- **A** — Absent
- **AL** — Attendance submitted after the allowed shift window
- **HD / WO / H** — Half day / week off / holiday (available as audited admin overrides)
- **N/A** — Employee inactive
- **—** — Today/future with no submission yet

An approved flagged submission counts as P/L; a rejected flagged submission counts as A.

## Attendance groups and monthly review

Attendance is tracked only for Field Supervisors (FS), Local Supervisors (LS), and
Local Supervisor Scanning (LSS). Project Co-Ordinators (PCs) remain available as
team profiles and assignment parents: FS, LS, and LSS report directly to a PC.
PCs do not submit attendance, have attendance
locations or shifts, receive absence records, or require face enrollment. If a PC
sends an attendance image, the system replies that attendance is not required and
does not process or store it as an attendance submission.
Participant deletion is blocked only by current attendance entries, overrides, or
child assignments; superseded image attempts remain as audit history and do not
prevent deletion. Coordinator profiles can be deleted once their roster participants
are reassigned; historical PC absence entries are retained but do not block deletion.
Legacy roster entries without a stored department retain the compatible FS default;
review and reassign these entries in Attendance Participants before relying on historical
department totals.

The admin Attendance page provides a monthly grid and an Excel export with one tab
for each group. Automated submissions remain the source result unless an admin
changes a grid cell. Each override requires a reason and is stored separately with
the prior code, admin identity, and timestamp so the original submission remains
available for audit.

## Fraud and evidence checks

Each initial image submission is analyzed. If a same-day submission is flagged and awaiting review, the employee can send a replacement; the earlier attempt remains stored as superseded audit data and its flag reason is linked to the replacement attendance record and confirmation reply. A verified submission or manual attendance override prevents another same-day attendance submission. Evidence includes:

- attendance date based on the processing day; server/WhatsApp `received_at_utc` retained for audit
- OCR-visible photo date comparison against the processing date
- EXIF date cross-check against the OCR-visible date, when metadata is available
- perceptual image hash compared with earlier submissions to detect likely photo reuse
- possible date-edit signal when a near-identical previous image has a conflicting overlay date
- face presence/count and enrolled-identity verification
- assigned city/district check from the GPS place text on attendance photos; no fixed-radius check
- unique WhatsApp phone numbers for unambiguous attendance matching
- passive image-quality/liveness risk signals
- human-readable fraud flags

A still image cannot prove hardware-backed real-time liveness; suspicious passive signals are therefore review flags, not a liveness guarantee.
EXIF and visible overlay data can both be manipulated or removed, so date cross-checks are review signals rather than proof of authenticity.

## Prerequisites on Windows

- Python **3.12**
- Node.js **20+**
- MongoDB **7/8** locally or a reachable MongoDB deployment
- Redis **7/8** locally
- Tesseract OCR
- Git is optional

Docker is optional for local development. Production deployment can use the supplied Docker Compose configuration.

## Fresh Windows PowerShell setup

```powershell
cd <extracted-folder>

cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
Copy-Item .env.example .env
pip install -r requirements.txt
```

Edit `backend\.env` and set the real credentials. Do not commit `.env`.

Install frontend dependencies:

```powershell
cd ..
rontend
npm install
```

## Start local services

Start MongoDB using your installed MongoDB service/application.

Start Redis using your local Redis installation. If Redis is installed as a Windows service, start that service. If using WSL, run Redis inside WSL. Docker is optional:

```powershell
docker run -d --name attendance-redis -p 127.0.0.1:6379:6379 redis:8-alpine redis-server --appendonly yes
```

Then use separate PowerShell terminals:

```powershell
# Terminal 1 - API
cd <project>ackend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
# Terminal 2 - AI worker
cd <project>ackend
.\.venv\Scripts\Activate.ps1
$env:WORKER_CONSUMER_NAME="attendance-worker-1"
python -m app.worker
```

```powershell
# Terminal 3 - notification worker
cd <project>ackend
.\.venv\Scripts\Activate.ps1
$env:NOTIFICATION_CONSUMER_NAME="notification-worker-1"
python -m app.notification_worker
```

```powershell
# Terminal 4 - React
cd <project>
rontend
npm run dev
```

Open `http://localhost:5173`.

For multiple AI workers, run another `python -m app.worker` with a different `WORKER_CONSUMER_NAME`. Redis Streams consumer groups distribute messages safely.

## Tesseract

Install Tesseract OCR and set:

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

If `tesseract.exe` is on PATH, leave `TESSERACT_CMD` empty.

## MongoDB indexes

FastAPI startup calls `ensure_indexes()` and safely creates/updates indexes for roster, submissions, image fingerprints, webhook idempotency and notification jobs. Existing collections/data are not dropped.

## Production HTTPS / Nginx

The production flow is:

```text
https://your-domain/
https://your-domain/webhook/interakt
```

Nginx terminates TLS and proxies the webhook/admin traffic to FastAPI. Use a real certificate and domain; do not use ngrok as the production ingress.

The production Compose file starts the backend, workers, frontend, Nginx,
Redis, and the configured database service. Deployment configuration, secrets,
TLS, and the Interakt webhook URL are documented in
[`PRODUCTION_DEPLOYMENT.md`](PRODUCTION_DEPLOYMENT.md).

### CMS account setup and access roles

Create the initial bootstrap account from the running backend container:

```powershell
docker compose --env-file backend/.env -f deploy/docker-compose.production.yml exec backend python scripts/create_admin.py
```

Sign in with that account and open **User access** to create credentials for staff. Account creation is only available to authorized signed-in users; there is no public registration. `manual_team` accounts can review and change attendance and participant records; `viewer` accounts can view attendance, monthly grids, coordinators, and participants only. Only the bootstrap super-admin can grant manual-team access. Share the assigned credentials with the intended staff member.

## WhatsApp / Interakt

Configure Interakt to POST signed `message_received` webhooks to:

```text
https://YOUR_DOMAIN/webhook/interakt
```

Set `INTERAKT_WEBHOOK_SECRET` and `INTERAKT_API_KEY` only in `.env`/secret storage.

## Admin review

Attendance location policy: pass within the employee-specific range (default 8 km, editable when needed); otherwise compare the GPS-derived city/town with the registered city/town. A mismatch or unavailable lookup is flagged for manual review. Lookups are cached and rate-limited; within-range attendance does not call the geocoding service. A Field Supervisor can disable location checks for their account; photo date/time and face checks still apply.

The React Attendance page shows P/L/F/A/N/A status for returned submission records and exposes human-readable reasons. Flagged records can be approved or rejected, and admins can permanently delete an individual attendance record from the table. Review details include server received time, OCR time, city/district location result, liveness and duplicate/reuse evidence. Face embedding vectors are never returned to the frontend.

## Fraud test checklist

1. Valid current photo, correct person/location -> **P**
2. Valid photo after shift grace -> **L**
3. Wrong person -> **F**
4. Wrong GPS -> **F**
5. Previous-day photo -> **F**
6. Exact same image from a different attendance day -> **F** and audited as possible reuse
7. Resized/recompressed near-duplicate -> **F** when pHash remains within threshold
8. Current-looking edited date over an old near-identical photo -> **F / possible_date_edit** when evidence supports it
9. Flagged pending photo followed by a new same-day image -> replacement is analyzed; prior attempt is retained as superseded
10. Verified attendance followed by another same-day image -> second attendance is blocked
11. Blurry photo -> **F**
12. No face -> **F**
13. Multiple faces -> **F**
14. Suspicious passive liveness/image characteristics -> **F**
15. No submission on a past day -> **A** in the export grid
16. Inactive employee -> **N/A**
17. Admin approval of F -> P/L; rejection -> A

## Troubleshooting

- `degraded` health: check MongoDB and Redis connectivity.
- Redis connection refused: verify Redis is listening on `127.0.0.1:6379` and `REDIS_URL`.
- OCR unavailable: verify Tesseract installation and `TESSERACT_CMD`.
- Face model startup errors: verify `insightface` and `onnxruntime` installation and the model runtime supported by the host.
- Webhook 401: verify the exact Interakt signature header/secret configuration.
- Workers not consuming: verify Redis is reachable and that all workers use the same stream/group but unique consumer names.

Shift defaults (IST): LSS 07:00–15:00 with 60 minutes grace; LS/FS 09:00–19:00 with 240 minutes grace. New registrations and role changes prefill these values; explicit employee overrides remain supported. Grace is measured after shift start. Existing P/L/AL classification is unchanged.

Field Supervisors (FS) have an Enable location check toggle, on by default. When disabled, missing GPS/assignment, range and city lookup do not flag attendance; the submission records location as disabled. Photo date/time, face, duplicate, liveness and shift checks remain active. LS/LSS cannot bypass location checking. Existing attendance records are unchanged by toggling this setting.

Employee WhatsApp replies are limited to flagged submissions and Absent due to late check-in (`absent_late`). Present, Late, ordinary Absent, accepted replacement photos, coordinator information, and already-submitted acknowledgments stay silent. The notification worker rechecks persisted attendance before sending, skips obsolete/routine queued replies, and uses a dedicated late-absence message. Existing admin alerts are unchanged.
