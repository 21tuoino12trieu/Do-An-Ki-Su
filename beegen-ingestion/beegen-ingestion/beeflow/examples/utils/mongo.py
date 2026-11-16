import base64
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from examples.utils.nlp import clean_json_string

def save_content(
    page_content: str,
    page_number: int,
    document_id: str
) -> Dict[str, Any]:
    """
    Build a MongoDB FIND_ONE_AND_UPDATE (pipeline update) payload that performs
    an idempotent "upsert per page"

    Args:
        page_content (str): Extracted text of the current page.
        page_number (int): The page index corresponding to the extracted text.
        document_id (str): The target document’s identifier in MongoDB (_id).

    Returns:
        filter (dict): <document_id>
        update (dict):  pipeline update
        options (dict): upsert options
    """
    return {
        "filter": {"_id": document_id},
        "update": [
            {
                "$set": {
                    "pages": {
                        "$concatArrays": [
                            {
                                "$filter": {
                                    "input": {"$ifNull": ["$pages", []]},
                                    "as": "p",
                                    "cond": {"$ne": ["$$p.page_number", page_number]}
                                }
                            },
                            [ {"page_number": page_number, "content": page_content} ]
                        ]
                    },
                    "last_updated_time": datetime.utcnow()
                }
            }
        ],
        "options": {"upsert": True}
    }
def save_metadata(
    document_id: str,
    document_path: str,
    document_type: str,
    document_name: str,
    total_pages: int
) -> Dict[str, Any]:
    """
    Format parameters for MongoOperation.FIND_ONE_AND_UPDATE to store document metadata

    Args:
        document_id (str): Unique ID of the document (used as _id in filter).
        document_path (str): Full path to the document (e.g., S3 URI).
        document_type (str): Type of the document (e.g., 'pdf', 'image').
        document_name (str): Name of the document file.
        total_pages (int): Total number of pages in the document.
        pages (List[Dict[str, Any]]): A list of page dictionaries containing page-wise metadata.

    Returns:
        filter (Dict[str, str]): A dictionary containing the ID of the document to filter,
        update (Dict[str, Any]): A dictionary containing the update logic for the document.
    """
    return {
            "filter": {"_id": document_id},
            "update": {
                "$set": {
                    "document_path": document_path,
                    "document_type": document_type,
                    "document_name": document_name,
                    "total_pages": total_pages,
                    "last_updated_time": datetime.utcnow()
                }
            }
        }

def load_content(document_id: str) -> Dict[str, Any]:
    """
    Build a MongoDB query to retrieve only the `content` field
    inside the `pages` array for a specific document.

    Args:
        document_id (str): Unique ID of the document (_id in MongoDB).

    Returns:
        filter (Dict[str, Any]): Matches the document with the given `_id`.
        projection (Dict[str, Any]): Includes only the `pages.content` field and excludes `_id` from the result.
    """
    return {
        "filter": {
            "_id": document_id
        },
        "projection": {
            "pages.content": 1,
            "_id": 0
        }
    }

def check_content(
    document_id: str,
) -> Dict[str, Any]:
    """
    Create a MongoDB filter to find a document by its document_id and check
    if the `pages` array contains at least one element with a `content` field.

    Args:
        document_id (str): Unique ID of the document (_id in MongoDB).

    Returns:
        filter (Dict[str, Any]): A MongoDB filter dictionary using $elemMatch and $exists
                        to detect the presence of `pages.content`.
    """
    return {
        "filter": {
            "_id": document_id,
            "pages": {
                "$elemMatch": {
                    "content": {"$exists": True}
                }
            }
        },
    }

def save_schema(
    schema: str,
    document_id: str
) -> Dict[str, Any]:
    """
    Format extracted document schema into MongoOperation.FIND_ONE_AND_UPDATE format.

    Args:
        schema (Dict[str, Any]): Extracted schema fields.
        document_id (str): Unique ID of the document (_id in MongoDB).

    Returns:
        filter (Dict[str, str]): A dictionary containing the ID of the document to filter,
        update (Dict[str, Any]): A dictionary containing the update logic for the document.
    """
    return {
        "filter": {"_id": document_id},
        "update": {
            "$set": {
                "schema": json.loads(clean_json_string(schema)),
                "last_updated_time": datetime.utcnow()
            }
        },
    }