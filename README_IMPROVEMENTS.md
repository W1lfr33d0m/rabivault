# RabiVault improvement patch

This patch improves the current Django/MinIO UI stack without changing the database structure of documents.

## What it changes

- Fixes `.env.example` so `MINIO_BUCKET_NAME` and `AWS_STORAGE_BUCKET_NAME` both use `rabivault-files`.
- Adds `.gitignore` rules for local backups and SQL dumps.
- Adds automatic MinIO bucket creation using both `minio-init` and a Django command: `ensure_minio_bucket`.
- Adds MFA setup and session verification screens using `django-otp` TOTP devices and QR codes.
- Redirects protected actions to MFA setup or MFA verification instead of blocking users with a dead-end message.
- Improves upload form UX: PowerPoint, CSV, DICOM, imaging metadata, date pickers, and comma-separated tags.
- Adds safer folder/facility validation.
- Adds pagination to file manager and audit logs.
- Improves audit log UI.

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

## Important cleanup

Your repository still contains tracked database backups. They should not be committed to Git.

After applying the patch, run:

```powershell
git rm --cached -r backups
git add .gitignore .env.example docker-compose.yml backend
git commit -m "Improve RabiVault UI, MFA setup, and MinIO startup"
```

Do not commit your real `.env` file.
