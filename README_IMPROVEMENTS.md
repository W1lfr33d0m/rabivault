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
- **DICOM / medical imaging** — Orthanc PACS server integration for receiving and viewing DICOM studies (DICOM protocol + web viewer), with imaging-study metadata (modality, study date, patient identifier, accession number, UID) tracked against documents. The viewer is tenant-isolated the same way the file manager is: a user only sees studies belonging to their own organization/facility (see §6).
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

## 6. Multi-tenant imaging isolation (Orthanc)

Before this change, the "Orthanc Viewer" sidebar link sent every user with imaging access to the *same* Orthanc login, shared across all organizations. Once inside, Orthanc's own UI has no concept of RabiVault's organization/facility model, so anyone with that link could browse every org's DICOM studies — the one part of the app that didn't have the same tenant isolation as the file manager. This section applies that isolation to imaging, verified end-to-end against a real running stack (two orgs, real tokens, real cross-tenant denial) rather than just wired up and assumed to work.

**How it works:** Orthanc's own username/password login is now off entirely. Every request Orthanc receives — including from its viewer UI — is authorized per-request by Orthanc's **Authorization plugin**, which calls back into two new Django webhooks (`apps/imaging/views.py`) asking "who holds this token, and which labels can they see." Each `ImagingStudy` is tagged in Orthanc with `org-<id>`/`facility-<id>` labels (pushed by a Celery task whenever the record is saved), and a user's permitted label set mirrors `apps/vault/permissions.py`'s role logic exactly: `platform_admin` → everything (`*`), `org_admin`/`auditor` → their whole org, everyone else → only the specific facilities they're assigned to. Opening the viewer mints a short-lived, single-purpose bearer token (only its hash is stored, never the raw value) and redirects into Orthanc's Explorer 2 UI already scoped to what that token permits — so the study list, search, and direct study access are all filtered server-side, not just hidden in RabiVault's own UI.

- **New models** (`apps/imaging/models.py`): `OrthancAccessToken` (hashed, expiring, per-user viewer session tokens) and an `orthanc_labels()` helper on `ImagingStudy`.
- **New permission module** (`apps/imaging/permissions.py`): `studies_for_user()` / `user_can_view_study()` / `labels_for_user()`, a direct mirror of the vault app's `documents_for_user()` / `user_can_view_document()` split (list-level and object-level checks). The shared `get_user_profile()` / `user_can_access_organization()` / `user_can_access_facility()` helpers were pulled out of `apps/vault/permissions.py` into a new `apps/organizations/permissions.py` so both apps use the same logic instead of duplicating it.
- **New views** (`apps/imaging/views.py`): a study list (`/imaging/studies/`) scoped to the logged-in user's org/facilities, a per-study "open" action that checks permission and audit-logs the specific study before minting a token, and the two Orthanc-facing webhooks (`user/get-profile`, `tokens/validate`) plus a no-op `tokens/decode` stub. The webhooks are protected by HTTP Basic Auth (`ORTHANC_WEBHOOK_USERNAME`/`PASSWORD`) so only the real Orthanc instance can call them.
- **New Orthanc REST client** (`apps/imaging/orthanc_client.py`) + Celery task/signal (`tasks.py`, `signals.py`): pushes an `ImagingStudy`'s org/facility labels onto the matching Orthanc study automatically on save, authenticating with a long-lived `ORTHANC_SERVICE_TOKEN` that the webhook recognizes as an all-access service identity (separate from per-user tokens).
- **`docker-compose.yml` / `docker-compose.prod.yml`**: the `orthanc` service now runs with `ORTHANC__AUTHENTICATION_ENABLED: "false"` and the Authorization plugin enabled (`AUTHORIZATION_PLUGIN_ENABLED`, `Authorization.WebServiceRootUrl` pointed at `web:8000/imaging/orthanc-auth/`, `CheckedLevel: studies`, `StandardConfigurations: ["orthanc-explorer-2"]`, `TokenHttpHeaders: ["token"]`) — config keys confirmed against the plugin's actual behavior in a throwaway container, not just its docs, which turned out to be incomplete in places (e.g. the `orthancteam/orthanc` image bundles the Authorization plugin, but Docker Hub's own page doesn't mention it).
- **Infrastructure fix (WSGI → ASGI):** Orthanc's Authorization plugin sends its webhook callbacks with `Transfer-Encoding: chunked`. Plain WSGI (Django's `runserver`, and gunicorn's default sync worker) has no way to read a chunked request body — there's no `Content-Length` for it to key off, so the body silently comes through empty and every webhook call was being denied. Both `docker-compose.yml` (dev) and `docker-compose.prod.yml` (prod) now run the app under ASGI instead: `uvicorn config.asgi:application --reload` in dev, `gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --workers 3` in prod. Verified against both the dev and prod command directly (not just the general claim that "ASGI supports chunked bodies").
- **`DJANGO_ALLOWED_HOSTS`** must include `web` (the docker-compose service name) even in production, since Orthanc calls back into Django as `http://web:8000/...` and Django rejects unrecognized `Host` headers by default. Already added to `.env`/`.env.example`/`DEPLOY.md`'s production block.
- **New required `.env` values**: `ORTHANC_SERVICE_TOKEN`, `ORTHANC_WEBHOOK_USERNAME`, `ORTHANC_WEBHOOK_PASSWORD` (generation commands are in `.env.example`), and `ORTHANC_INTERNAL_URL` (defaults to `http://orthanc:8042`, the docker-compose service address Django itself uses to reach Orthanc — distinct from the public-facing `ORTHANC_URL` browsers use). `ORTHANC_USERNAME`/`ORTHANC_PASSWORD` are no longer used and were removed.
- **Known limitation:** deep-linking straight to one specific study inside the Orthanc viewer isn't wired up — that would require also implementing Orthanc's separate "resource sharing token" mechanism (`tokens/decode` doing real work instead of a stub), which is a distinct feature from the login/session token this change adds. Opening a study from RabiVault currently lands you on the viewer's study list, already correctly filtered to what you're allowed to see, rather than the one study itself.

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
git add .gitignore .env.example docker-compose.yml docker-compose.prod.yml DEPLOY.md backend
git commit -m "Improve RabiVault UI, MFA setup, and MinIO startup"
```

Do not commit your real `.env` file.
