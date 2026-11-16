import base64
from typing import Any, Dict, List


def document_preprocessed(document_id: str, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract image data from pages for S3 upload.

    Args:
        document_id (str): Unique ID of the document.
        pages (List[Dict[str, Any]]): List of pages, each possibly containing 'image_data'.

    Returns:
        batch_data (Dict[str, Any]): A dictionary with keys: key, content, content_type
    """
    uploads = []
    for idx, page in enumerate(pages, start=1):
        image_data = page.get("image_data")
        if image_data:
            uploads.append({
                "bucket": "ai-knowledge-working",
                "key": f"rnd/thaivd/work/cua/preprocessed/{document_id}/page_{idx}.png",
                "content_base64": image_data,
                "content": base64.b64decode(image_data),
                "page_number": int(page.get("page_number")),
                "content_type": "image/png",
                "document_id": document_id
            })
    return {"batch_data": uploads}