import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the configured MinIO/S3 bucket if it does not already exist."

    def handle(self, *args, **options):
        bucket = settings.AWS_STORAGE_BUCKET_NAME

        if not bucket:
            raise CommandError("AWS_STORAGE_BUCKET_NAME is not configured.")

        client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        try:
            existing = [item["Name"] for item in client.list_buckets().get("Buckets", [])]
        except ClientError as exc:
            raise CommandError(f"Unable to list buckets: {exc}") from exc

        if bucket in existing:
            self.stdout.write(self.style.SUCCESS(f"Bucket already exists: {bucket}"))
            return

        try:
            client.create_bucket(Bucket=bucket)
        except ClientError as exc:
            raise CommandError(f"Unable to create bucket {bucket}: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Created bucket: {bucket}"))
