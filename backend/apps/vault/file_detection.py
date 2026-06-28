from pathlib import Path
import csv
import zipfile

import filetype


EXTENSION_TO_DOCUMENT_TYPE = {
    ".pdf": "pdf",
    ".doc": "document",
    ".docx": "document",
    ".txt": "document",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".csv": "spreadsheet",
    ".ppt": "presentation",
    ".pptx": "presentation",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".dcm": "dicom",
    ".dicom": "dicom",
    ".zip": "archive",
}


def _read_start(uploaded_file, size=4096):
    current_position = uploaded_file.tell()
    uploaded_file.seek(0)
    data = uploaded_file.read(size)
    uploaded_file.seek(current_position)
    return data


def _is_dicom(uploaded_file):
    current_position = uploaded_file.tell()
    uploaded_file.seek(128)
    marker = uploaded_file.read(4)
    uploaded_file.seek(current_position)
    return marker == b"DICM"


def _detect_office_zip(uploaded_file):
    current_position = uploaded_file.tell()
    uploaded_file.seek(0)

    try:
        with zipfile.ZipFile(uploaded_file) as z:
            names = set(z.namelist())

            if "word/document.xml" in names:
                return "document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

            if "xl/workbook.xml" in names:
                return "spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            if "ppt/presentation.xml" in names:
                return "presentation", "application/vnd.openxmlformats-officedocument.presentationml.presentation"

            return "archive", "application/zip"

    except zipfile.BadZipFile:
        return None, None

    finally:
        uploaded_file.seek(current_position)


def detect_uploaded_file(uploaded_file):
    """
    Returns:
        {
            "document_type": "pdf" | "document" | "spreadsheet" | "presentation" | "image" | "dicom" | "archive" | "other",
            "mime_type": "...",
            "extension": ".pdf",
            "confidence": "high" | "medium" | "low",
        }
    """

    extension = Path(uploaded_file.name).suffix.lower()
    start = _read_start(uploaded_file)

    if _is_dicom(uploaded_file):
        return {
            "document_type": "dicom",
            "mime_type": "application/dicom",
            "extension": extension,
            "confidence": "high",
        }

    kind = filetype.guess(start)

    if kind:
        if kind.mime == "application/pdf":
            return {
                "document_type": "pdf",
                "mime_type": kind.mime,
                "extension": extension,
                "confidence": "high",
            }

        if kind.mime.startswith("image/"):
            return {
                "document_type": "image",
                "mime_type": kind.mime,
                "extension": extension,
                "confidence": "high",
            }

        if kind.mime == "application/zip":
            document_type, mime_type = _detect_office_zip(uploaded_file)
            return {
                "document_type": document_type or "archive",
                "mime_type": mime_type or "application/zip",
                "extension": extension,
                "confidence": "high",
            }

    if extension == ".csv":
        return {
            "document_type": "spreadsheet",
            "mime_type": "text/csv",
            "extension": extension,
            "confidence": "medium",
        }

    if extension == ".txt":
        return {
            "document_type": "document",
            "mime_type": "text/plain",
            "extension": extension,
            "confidence": "medium",
        }

    return {
        "document_type": EXTENSION_TO_DOCUMENT_TYPE.get(extension, "other"),
        "mime_type": "application/octet-stream",
        "extension": extension,
        "confidence": "low",
    }