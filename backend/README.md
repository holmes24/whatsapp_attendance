# Backend

FastAPI APIs and Redis Streams workers for attendance photo processing. SQL Server is the only supported system of record.

The backend uses SQL Server through ODBC Driver 18. Set `MSSQL_SERVER`, `MSSQL_DATABASE`, `MSSQL_USERNAME`, `MSSQL_PASSWORD`, `MSSQL_ENCRYPT`, and `MSSQL_TRUST_SERVER_CERTIFICATE` in the deployment secret store. The database must exist before startup; the app creates its tables and indexes inside that database only.

The webhook validates Interakt signatures and queues events. Workers perform OCR, face verification, GPS/city checks, duplicate-photo checks, passive image checks, attendance classification and notifications.

For production deployment, see the repository root `PRODUCTION_DEPLOYMENT.md`. For regression checks, install `requirements-test.txt` and run `python -m pytest tests -q -p no:cacheprovider` from this directory.
