from collections.abc import Iterable
from typing import Any

from beegen.configs.storage.mongo_config import MongoConfig
from fastapi import HTTPException, status
from pymongo import MongoClient


def get_mongo_db() -> Any:
    config = MongoConfig.default()
    client = MongoClient(config.uri)
    return client[config.authen_source]


def validate_bot(bot_id: str) -> None:
    db = get_mongo_db()
    bot = db["botinfo"].find_one({"_id": bot_id})
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )
    if bot.get("deleted") is True:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot has been deleted",
        )


def _get_resources(
    collection_name: str,
    resource_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    db = get_mongo_db()
    resources = db[collection_name].find({"_id": {"$in": list(resource_ids)}})
    return {resource["_id"]: resource for resource in resources}


def _validate_resources(
    *,
    collection_name: str,
    resource_name: str,
    bot_id: str,
    resource_ids: list[str],
    require_deleted: bool | None,
    resources: dict[str, dict[str, Any]] | None = None,
) -> None:
    if resources is None:
        resources = _get_resources(collection_name, resource_ids)

    for resource_id in resource_ids:
        resource = resources.get(resource_id)
        if resource is None or resource.get("bot_id") != bot_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{resource_name} not found",
            )

        is_deleted = resource.get("deleted") is True
        if require_deleted is True and not is_deleted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{resource_name} has not been deleted",
            )
        if require_deleted is False and is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{resource_name} has been deleted",
            )


def _get_active_documents(
    bot_id: str,
    document_ids: list[str],
) -> dict[str, dict[str, Any]]:
    resources = _get_resources("documents", document_ids)
    _validate_resources(
        collection_name="documents",
        resource_name="Document",
        bot_id=bot_id,
        resource_ids=document_ids,
        require_deleted=False,
        resources=resources,
    )
    return resources


def validate_active_documents(bot_id: str, document_ids: list[str]) -> None:
    _get_active_documents(bot_id, document_ids)


def validate_documents_for_train(bot_id: str, document_ids: list[str]) -> None:
    resources = _get_active_documents(bot_id, document_ids)

    not_ready = [
        {
            "document_id": document_id,
            "status": resources[document_id].get("status"),
        }
        for document_id in document_ids
        if resources[document_id].get("status") != "DONE"
    ]
    if not_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "One or more documents have not been chunked",
                "documents": not_ready,
            },
        )

    trained_document_ids = [
        document_id
        for document_id in document_ids
        if resources[document_id].get("is_trained") is True
        and resources[document_id].get("training_status") == "DONE"
    ]
    if trained_document_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "One or more documents have already been trained",
                "document_ids": trained_document_ids,
            },
        )


def validate_documents_for_clean(bot_id: str, document_ids: list[str]) -> None:
    _validate_resources(
        collection_name="documents",
        resource_name="Document",
        bot_id=bot_id,
        resource_ids=document_ids,
        require_deleted=None,
    )


def validate_active_dialogues(bot_id: str, dialogue_ids: list[str]) -> None:
    _validate_resources(
        collection_name="dialogue",
        resource_name="Dialogue",
        bot_id=bot_id,
        resource_ids=dialogue_ids,
        require_deleted=False,
    )


def validate_dialogues_for_clean(bot_id: str, dialogue_ids: list[str]) -> None:
    _validate_resources(
        collection_name="dialogue",
        resource_name="Dialogue",
        bot_id=bot_id,
        resource_ids=dialogue_ids,
        require_deleted=True,
    )
