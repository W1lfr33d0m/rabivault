import boto3
from django.conf import settings
import hashlib
import pyclamd
from django.conf import settings


"""def scan_file_with_clamav(file_path):
    scanner = pyclamd.ClamdNetworkSocket(
        host=settings.CLAMAV_HOST,
        port=settings.CLAMAV_PORT,
    )

    result = scanner.scan_file(file_path)

    if result is not None:
        return False, result

    return True, None"""

def scan_file_stream_with_clamav(file_obj):
    scanner = pyclamd.ClamdNetworkSocket(
        host=getattr(settings, "CLAMAV_HOST", "clamav"),
        port=getattr(settings, "CLAMAV_PORT", 3310),
    )

    file_obj.seek(0)
    result = scanner.instream(file_obj)

    if result is not None:
        return False, result

    return True, None


def calculate_sha256(uploaded_file):
    sha256 = hashlib.sha256()

    for chunk in uploaded_file.chunks():
        sha256.update(chunk)

    uploaded_file.seek(0)

    return sha256.hexdigest()

def generate_presigned_download_url(document, expires_in=300):
    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    return s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": document.file.name,
            "ResponseContentDisposition": f'attachment; filename="{document.original_filename or document.file.name}"',
        },
        ExpiresIn=expires_in,
    )