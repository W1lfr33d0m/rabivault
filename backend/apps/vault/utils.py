import hashlib


def calculate_sha256(uploaded_file):
    sha256 = hashlib.sha256()

    for chunk in uploaded_file.chunks():
        sha256.update(chunk)

    uploaded_file.seek(0)

    return sha256.hexdigest()
