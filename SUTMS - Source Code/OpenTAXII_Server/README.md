# Simple TAXII-like server (Flask + MySQL)

This project provides a minimal TAXII2-like HTTP server that stores STIX2 objects in a MySQL database and exposes simple collection endpoints.

It is intentionally small and easy to run locally. The app is not a full-featured production-grade TAXII server, but can host and serve STIX/TAXII IoC feeds and be extended.

## What you'll find

- `app.py` - Flask server with minimal TAXII2-like endpoints
- `models.py` - SQLAlchemy models for collections and stix objects
- `config.py` - DB configuration (reads env vars) — update credentials here or via environment variables
- `db_init.py` - creates tables
- `ingest_sample.py` - ingests `sample_data/sample_bundle.json` into the DB
- `docker-compose.yml` - runs a MySQL database (DB only; app runs on host)
- `requirements.txt` - Python dependencies

## Quick start (Windows PowerShell)

1. Start MySQL via Docker Compose

```powershell
# from project root (this repo)
docker-compose up -d
```

2. Create a virtualenv and install dependencies

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Configure DB credentials

Open `config.py` and update values or set environment variables. Defaults match `docker-compose.yml`:

- MYSQL_USER: taxii_user
- MYSQL_PASSWORD: taxii_pass
- MYSQL_HOST: 127.0.0.1
- MYSQL_PORT: 3306
- MYSQL_DB: taxii_db

You can set environment variables instead, e.g.:

```powershell
$env:MYSQL_USER = 'taxii_user'; $env:MYSQL_PASSWORD = 'taxii_pass'
```

4. Initialize DB tables

```powershell
python db_init.py
```

5. Ingest sample STIX bundle

```powershell
python ingest_sample.py
```

6. Run the server

```powershell
python app.py
```

Server will listen on http://127.0.0.1:5000

## Endpoints (minimal)

- GET `/taxii/` — API root with server info
- GET `/taxii/collections` — list of collections (id, title, description)
- GET `/taxii/collections/<collection_id>/objects` — returns a STIX bundle JSON containing objects for that collection
  - query params: `limit` (default 50), `offset` (default 0)

Example:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/taxii/collections
Invoke-RestMethod http://127.0.0.1:5000/taxii/collections/default_collection/objects?limit=10&offset=0
```

## Where to update credentials

- `config.py` reads credentials from environment variables by default. Edit `config.py` only if you want to change defaults.

## Notes

- This is a minimal service meant for development and testing of STIX/TAXII feeds. For production, add authentication, TLS, robust paging, error handling, rate limiting, and conform strictly to the TAXII2 spec or run a vetted implementation like OpenTAXII where appropriate.

If you want, I can now start the database container and run a smoke test locally (will try to start Docker). Let me know if you want me to run those steps now.