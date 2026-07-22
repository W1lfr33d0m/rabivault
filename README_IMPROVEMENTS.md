# RabiVault improvement patch

This patch improves the current Django/MinIO UI stack without changing the database structure of documents.

## Website features

A Django-based secure document vault for medical organizations, multi-tenant across organizations and facilities.

- **Document vault** — upload, browse, and search documents; organize into folders; comma-separated tagging; per-document metadata (title, category, facility, expiry/retention dates). File type is detected from actual file content (magic bytes/DICOM header/zip contents), not just the extension, with a `500 MB` per-file limit and an allow-list of extensions.
- **Antivirus scanning** — every upload is scanned by ClamAV before it's usable; documents show a scan status (pending/clean/failed).
- **Integrity & lifecycle** — SHA-256 checksum on upload, soft-delete with restore, retention/expiry dates per document.
- **Access control** — role-based permissions (`platform_admin`, `org_admin`, `facility_manager`, `staff`, `external_reviewer`, `auditor`) scoped to organization and facility, with object-level checks (django-guardian) before view/upload/download.
- **MFA** — TOTP-based two-factor authentication (QR code enrollment via `django-otp`), required for every user before sensitive actions.
- **Login security** — rate-limited login (brute-force protection), Django password-strength validation, 30-minute idle session timeout, CSRF protection on every form.
- **Audit logging** — tamper-evident, hash-chained log of logins, views, downloads, uploads, deletes, restores, permission changes, and MFA events, with actor/IP/user-agent capture; filterable, paginated audit log UI for compliance review.
- **DICOM / medical imaging** — Orthanc PACS server integration for receiving and viewing DICOM studies (DICOM protocol + web viewer), with imaging-study metadata (modality, study date, patient identifier, accession number, UID) tracked against documents.
- **Compliance record-keeping** (Django-admin managed) — Business Associate Agreement tracking, per-document-type retention policies, periodic access reviews, and security-incident logging.
- **Backups** — scheduled, GPG-encrypted PostgreSQL backups, with a model for logging backup-restore test results.
- **Storage** — S3-compatible object storage (MinIO), with server-side encryption at rest for stored documents.
- **Deployment** — Docker Compose for local development; a separate production Compose file with Gunicorn, WhiteNoise, and a Caddy reverse proxy for automatic HTTPS on a VPS.

## 1. Original UI & MinIO improvements

- Fixes `.env.example` so `MINIO_BUCKET_NAME` and `AWS_STORAGE_BUCKET_NAME` both use `rabivault-files`.
- Adds `.gitignore` rules for local backups and SQL dumps.
- Adds automatic MinIO bucket creation using both `minio-init` and a Django command: `ensure_minio_bucket`.
- Adds MFA setup and session verification screens using `django-otp` TOTP devices and QR codes.
- Redirects protected actions to MFA setup or MFA verification instead of blocking users with a dead-end message.
- Improves upload form UX: PowerPoint, CSV, DICOM, imaging metadata, date pickers, and comma-separated tags.
- Adds safer folder/facility validation.
- Adds pagination to file manager and audit logs.
- Improves audit log UI.

## 2. Post-review fixes (file handling & permissions)

A code review of this branch found a few issues, since fixed:

- Document uploads now use the sniffed file type from `file_detection.py` (magic bytes/DICOM header/zip contents) instead of a discarded extension-only guess, so `document_type` reflects the file's actual content.
- Restored the `500 MB` per-file upload size limit in `DocumentUploadForm.clean_file`, which had been dropped, so it matches what the upload page tells users.
- Pinned `filetype` and `pydicom` in `requirements.txt` (`==1.2.0` / `==3.0.2`) instead of leaving them unversioned like every other dependency in that file.
- Fixed file manager and audit log pagination links to `|urlencode` the search/filter values, so a query containing `&`, `+`, or `#` no longer corrupts the page-2 URL.
- Reordered `document_upload` so the folder/facility permission checks run before the document is saved, instead of save-then-check-then-save-again.

## 3. Branding

- Added `backend/static/img/logo.png` (160×160, resized down from a 1.7 MB source image) and a multi-resolution `backend/static/img/favicon.ico`.
- Sidebar and login-page logos now render the actual shield mark instead of the "RV" text placeholder; a browser-tab favicon was added via `<link rel="icon">` in `base.html`.
- `.logo-mark` CSS updated to fit an `<img>` (dropped the old gradient-background placeholder styling).

## 4. Production deployment (VPS + Docker Compose + Caddy)

- Added `docker-compose.prod.yml`: runs the same services as `docker-compose.yml` but with Gunicorn instead of `runserver`, no source bind-mounts, and Postgres/Redis/MinIO/ClamAV/Orthanc's HTTP port no longer published publicly — only reachable on the internal Docker network.
- Added a `caddy` service + `Caddyfile`: reverse-proxies your domain to `web` and an `orthanc.<domain>` subdomain to Orthanc's UI, automatically issuing/renewing Let's Encrypt TLS certificates.
- Added `gunicorn` and `whitenoise` to `requirements.txt`. Static files are now served by WhiteNoise from inside the `web` container (`CompressedManifestStaticFilesStorage`), so no shared static volume is needed with Caddy.
- `settings.py`: added a `DJANGO_USE_HTTPS` env flag gating `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/`SECURE_SSL_REDIRECT` (defaults to off, so local HTTP dev is unaffected), `SECURE_PROXY_SSL_HEADER` to trust Caddy's `X-Forwarded-Proto`, and `CSRF_TRUSTED_ORIGINS`.
- Added `DEPLOY.md`: step-by-step guide for provisioning a VPS, pointing DNS, configuring the firewall, filling in `.env`, deploying, creating an admin user, and setting up backups.

## 5. HIPAA-oriented security hardening

Technical-safeguard gaps found in a HIPAA-focused review, since fixed. (Full HIPAA compliance also requires a signed Business Associate Agreement with your host, a formal risk analysis, and written workforce policies — none of which are code changes.)

- MFA is now required for **every** user/role, not just `platform_admin`/`org_admin`/`facility_manager`/`auditor` (`apps/accounts/decorators.py`) — previously `staff` and `external_reviewer` accounts could upload/view/download documents without MFA.
- Login is now rate-limited (10 attempts/minute per IP) via `RateLimitedLoginView` (`apps/accounts/views.py`, wired in `config/urls.py`), closing a brute-force gap the existing per-user rate limits on upload/download/audit-list didn't cover.
- Added Django's standard password strength validators with a 12-character minimum (`AUTH_PASSWORD_VALIDATORS` — previously unset).
- Added a 30-minute idle session timeout: `SESSION_COOKIE_AGE` + `SESSION_SAVE_EVERY_REQUEST` (resets on each request) + `SESSION_EXPIRE_AT_BROWSER_CLOSE`.
- Fixed `get_client_ip()` in `apps/audit/utils.py` to use the *last* `X-Forwarded-For` entry (the one appended by Caddy) instead of the client-spoofable first one, protecting the integrity of the tamper-evident audit trail.
- Enabled MinIO's built-in KMS plus bucket-level default encryption (`MINIO_KMS_SECRET_KEY` + `mc encrypt set sse-kms` in `minio-init`), so uploaded documents are encrypted at rest transparently — verified against the actual running MinIO release before rolling out.
- `DEBUG` now defaults to `False` if the env var is ever missing, instead of `True` — the previous default could leak PHI in stack traces on a misconfigured deploy.
- Backups are now GPG-encrypted: `backup/Dockerfile` layers `gnupg` onto `postgres:16`, and `DEPLOY.md`'s cron example pipes `pg_dump` through AES-256 symmetric encryption using `BACKUP_ENCRYPTION_KEY` instead of writing a plain `.sql` file.
- New required `.env` values for the above: `MINIO_KMS_SECRET_KEY` and `BACKUP_ENCRYPTION_KEY` (generation commands are in `.env.example`).

## How to apply

Copy these files into your project, preserving the folder paths.

Then run:

```powershell
docker compose down
docker compose up -d --build
```

Then run:

```powershell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py ensure_minio_bucket
docker compose exec web python manage.py findstatic css/app.css
```

For a production deployment, use `docker-compose.prod.yml` instead — see `DEPLOY.md` for the full walkthrough (DNS, firewall, `.env`, TLS, backups).

## Important cleanup

Your repository still contains tracked database backups. They should not be committed to Git.

After applying the patch, run:

```powershell
git rm --cached -r backups
git add .gitignore .env.example docker-compose.yml backend
git commit -m "Improve RabiVault UI, MFA setup, and MinIO startup"
```

Do not commit your real `.env` file.
