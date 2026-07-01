import json
import requests
from django.conf import settings


DOCUMENT_CATEGORIES = [
    "purchase_order",
    "invoice",
    "contract",
    "radiation_safety",
    "mammography_qc",
    "training_material",
    "policy",
    "medical_record",
    "imaging_metadata",
    "spreadsheet",
    "presentation",
    "other",
]


def classify_document_with_ollama(title, document_type, extracted_text):
    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
    model = getattr(settings, "OLLAMA_MODEL", "llama3.2:3b")

    text_preview = (extracted_text or "")[:6000]

    prompt = f"""
You are classifying documents inside a medical facility data vault.

Return only valid JSON.

Allowed categories:
{", ".join(DOCUMENT_CATEGORIES)}

Document title:
{title}

Detected file type:
{document_type}

Document text preview:
{text_preview}

Return this JSON structure:
{{
  "category": "one_allowed_category",
  "confidence": 0.0,
  "summary": "short summary",
  "suggested_tags": ["tag1", "tag2", "tag3"],
  "contains_possible_phi": true,
  "reason": "brief reason"
}}
"""

    response = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        },
        timeout=120,
    )

    response.raise_for_status()
    data = response.json()

    raw_response = data.get("response", "{}")

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        parsed = {
            "category": "other",
            "confidence": 0,
            "summary": "",
            "suggested_tags": [],
            "contains_possible_phi": False,
            "reason": "Model returned invalid JSON.",
            "raw_response": raw_response,
        }

    if parsed.get("category") not in DOCUMENT_CATEGORIES:
        parsed["category"] = "other"

    return parsed