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

## Post-review fixes

A code review of this branch found a few issues, since fixed:

- Document uploads now use the sniffed file type from `file_detection.py` (magic bytes/DICOM header/zip contents) instead of a discarded extension-only guess, so `document_type` reflects the file's actual content.
- Restored the `500 MB` per-file upload size limit in `DocumentUploadForm.clean_file`, which had been dropped, so it matches what the upload page tells users.
- Pinned `filetype` and `pydicom` in `requirements.txt` (`==1.2.0` / `==3.0.2`) instead of leaving them unversioned like every other dependency in that file.
- Fixed file manager and audit log pagination links to `|urlencode` the search/filter values, so a query containing `&`, `+`, or `#` no longer corrupts the page-2 URL.
- Reordered `document_upload` so the folder/facility permission checks run before the document is saved, instead of save-then-check-then-save-again.

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
