# Deploying RabiVault to a VPS

This runs the existing Docker Compose stack on any Ubuntu VPS (DigitalOcean,
Hetzner, AWS Lightsail, etc.) with Caddy in front for automatic HTTPS. No
managed services required — everything (Postgres, MinIO, ClamAV, Orthanc)
runs in containers on the same box.

Recommended minimum size: 2 vCPU / 4 GB RAM (ClamAV's virus database alone
needs ~1-1.5 GB resident).

## 1. Point DNS at the server

Create A records pointing at the VPS's public IP:

- `vault.example.com` — the app
- `orthanc.vault.example.com` — Orthanc's web UI (optional, only if you want
  browser access to Orthanc; PACS/modalities talk to port 4242 directly and
  don't need this record)

Caddy won't be able to issue a TLS certificate until these resolve.

## 2. Provision the server

```bash
ssh root@your-server-ip

apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh

# Firewall: only SSH, HTTP/HTTPS, and DICOM (if needed) are public.
# Everything else (Postgres, Redis, MinIO, ClamAV, Orthanc's HTTP port) stays
# on the internal Docker network in docker-compose.prod.yml.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 4242/tcp   # only if an external PACS/modality sends studies here
ufw enable
```

## 3. Deploy the code

```bash
git clone <your-repo-url> rabivault
cd rabivault
cp .env.example .env
```

Edit `.env`:

- Set real, unique values for `SECRET_KEY`, `POSTGRES_PASSWORD`,
  `MINIO_ROOT_PASSWORD`/`AWS_SECRET_ACCESS_KEY`, `ORTHANC_PASSWORD`.
- Uncomment and fill in the production block at the top:
  ```
  DOMAIN=vault.example.com
  DJANGO_USE_HTTPS=True
  DJANGO_ALLOWED_HOSTS=vault.example.com
  CSRF_TRUSTED_ORIGINS=https://vault.example.com,https://orthanc.vault.example.com
  ```
- Set `DEBUG=False`.

Then build and start everything:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This runs migrations, creates the MinIO bucket, collects static files, and
starts the app behind Gunicorn — all before Caddy requests a certificate.

Create your first admin user:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

## 4. Verify

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs caddy --tail 50
```

Visit `https://vault.example.com` — Caddy should have already obtained a
Let's Encrypt certificate automatically. If it hasn't, check that DNS has
propagated and ports 80/443 are actually reachable from the internet.

## 5. Redeploying updates

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## 6. Backups

The `backup` container mounts `./backups` and stays idle (`sleep infinity`)
so you can run `pg_dump` inside it on a schedule, e.g. via a host cron job:

```bash
0 3 * * * docker compose -f /path/to/rabivault/docker-compose.prod.yml exec -T backup \
  pg_dump -h db -U $POSTGRES_USER -d $POSTGRES_DB > /path/to/rabivault/backups/db-$(date +\%F).sql
```

Also snapshot the named Docker volumes (`rabivault_postgres_data`,
`rabivault_minio_data`, `rabivault_orthanc_data`) at the infrastructure level
(e.g. your VPS provider's volume/disk snapshot feature) since they hold the
actual uploaded documents and DICOM studies, not just the database.

## Notes

- `docker-compose.yml` (the original file) stays as-is for local development
  — it uses `runserver`, publishes every service's port to `localhost` for
  convenience, and defaults to `DEBUG=True`/HTTP.
- `docker-compose.prod.yml` is the production variant: Gunicorn instead of
  `runserver`, no source bind-mounts, no public ports on Postgres/Redis/MinIO/
  ClamAV/Orthanc's HTTP port, and a Caddy container terminating TLS.
- Static files are served by WhiteNoise from inside the `web` container, so
  no static-file volume needs to be shared with Caddy.
