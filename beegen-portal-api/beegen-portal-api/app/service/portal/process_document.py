import asyncio
import os
import uuid
from typing import Any

import requests
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.workflow import WorkflowEngine
from fastapi import HTTPException, status

from app.model.document import CleanDataRequest, TrainRequest, UploadRequest
from app.utils.db_validation import (
    get_mongo_db,
    validate_active_documents,
    validate_bot,
    validate_documents_for_clean,
    validate_documents_for_train,
)


def _prepare_batch_data(ids: list, bot_id: str):
    return {"batch_data": [{"document_id": document_id, "bot_id": bot_id} for document_id in ids]}


def trigger_upload_document_dag(
    bot_id: str,
    document_ids: list[str],
) -> dict[str, str]:
    response = requests.post(
        f"{os.getenv('AIRFLOW_URL')}/dags/{os.getenv('AIRFLOW_UPLOAD_DOCUMENT_DAG')}/dagRuns",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {os.getenv('AIRFLOW_TOKEN')}",
        },
        json={
            "conf": {
                "bot_id": bot_id,
                "document_ids": document_ids,
            }
        },
        timeout=30,
        verify=False,
    )
    response.raise_for_status()
    dag_run = response.json()
    return {
        "dag_run_id": dag_run["dag_run_id"],
        "dag_state": dag_run["state"],
    }


def trigger_train_document_dag(
    bot_id: str,
    document_ids: list[str],
) -> dict[str, str]:
    response = requests.post(
        f"{os.getenv('AIRFLOW_URL')}/dags/{os.getenv('AIRFLOW_TRAIN_DOCUMENT_DAG')}/dagRuns",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {os.getenv('AIRFLOW_TOKEN')}",
        },
        json={
            "conf": {
                "bot_id": bot_id,
                "document_ids": document_ids,
            }
        },
        timeout=30,
        verify=False,
    )
    response.raise_for_status()
    dag_run = response.json()
    return {
        "dag_run_id": dag_run["dag_run_id"],
        "dag_state": dag_run["state"],
    }

def trigger_clean_document_dag(
    bot_id: str,
    document_ids: list[str],
) -> dict[str, str]:
    response = requests.post(
        f"{os.getenv('AIRFLOW_URL')}/dags/{os.getenv('AIRFLOW_CLEAN_DOCUMENT_DAG')}/dagRuns",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {os.getenv('AIRFLOW_TOKEN')}",
        },
        json={
            "conf": {
                "bot_id": bot_id,
                "document_ids": document_ids,
            }
        },
        timeout=30,
        verify=False,
    )
    response.raise_for_status()
    dag_run = response.json()
    return {
        "dag_run_id": dag_run["dag_run_id"],
        "dag_state": dag_run["state"],
    }

def _set_upload_processing(document_ids: list[str]) -> None:
    get_mongo_db()["documents"].update_many(
        {"_id": {"$in": document_ids}},
        {"$set": {"status": "PROCESS"}},
    )


def _set_training(document_ids: list[str]) -> None:
    get_mongo_db()["documents"].update_many(
        {"_id": {"$in": document_ids}},
        {"$set": {"is_trained": False, "training_status": "PROCESS"}},
    )


def _mark_unfinished_documents_error(
    document_ids: list[str],
    *,
    operation: str,
) -> None:
    if operation == "upload":
        query = {"_id": {"$in": document_ids}, "status": "PROCESS"}
        update = {"$set": {"status": "ERROR"}}
    else:
        query = {"_id": {"$in": document_ids}, "training_status": "PROCESS"}
        update = {"$set": {"is_trained": False, "training_status": "ERROR"}}
    get_mongo_db()["documents"].update_many(query, update)


async def _orchestrate_documents(
    ids: list[str],
    bot_id: str,
    operation: str,
) -> dict[str, Any]:
    try:
        if operation == "upload":
            await asyncio.to_thread(_set_upload_processing, ids)
            trigger_fn = trigger_upload_document_dag
        elif operation == "train":
            await asyncio.to_thread(_set_training, ids)
            trigger_fn = trigger_train_document_dag
        else:
            trigger_fn = trigger_clean_document_dag

        dag_run = await asyncio.to_thread(
            trigger_fn,
            bot_id=bot_id,
            document_ids=ids,
        )
        return {
            "dag_run_id": dag_run["dag_run_id"],
            "dag_state": dag_run["dag_state"],
        }
    except Exception as exc:
        if operation in ("upload", "train"):
            await asyncio.to_thread(
                _mark_unfinished_documents_error,
                ids,
                operation=operation,
            )
        raise exc

class ProcessDocumentService:
    def __init__(self) -> None:
        self._build_upload_document_workflow()
        self._build_train_document_workflow()
        self._build_clean_document_workflow()

    def _build_upload_document_workflow(self) -> None:
        with WorkflowEngine(
            name="wf_upload_document",
            description="upload documents and wait for results",
            langfuse="beegen-portal",
        ) as workflow:
            orchestrate = CodeNode(
                name="code_orchestrate_upload_documents",
                code_fn=_orchestrate_documents,
                inputs={
                    "ids": INPUT,
                    "bot_id": INPUT,
                    "operation": "upload",
                },
                return_keys=[
                    "dag_run_id: str",
                    "dag_state: str",
                ],
                outputs=OUTPUT,
            )
            START >> orchestrate >> END
        workflow.compile()
        self.upload_document_workflow = workflow

    def _build_train_document_workflow(self) -> None:
        with WorkflowEngine(
            name="wf_train_document",
            description="train documents and wait for results",
            langfuse="beegen-portal",
        ) as workflow:
            orchestrate = CodeNode(
                name="code_orchestrate_train_documents",
                code_fn=_orchestrate_documents,
                inputs={
                    "ids": INPUT,
                    "bot_id": INPUT,
                    "operation": "train",
                },
                return_keys=[
                    "dag_run_id: str",
                    "dag_state: str",
                ],
                outputs=OUTPUT,
            )
            START >> orchestrate >> END
        workflow.compile()
        self.train_document_workflow = workflow

    def _build_clean_document_workflow(self) -> None:
        with WorkflowEngine(
            name="wf_clean_document",
            description="clean deleted document records via Airflow DAG",
            langfuse="beegen-portal",
        ) as workflow:
            orchestrate = CodeNode(
                name="code_orchestrate_clean_documents",
                code_fn=_orchestrate_documents,
                inputs={
                    "ids": INPUT,
                    "bot_id": INPUT,
                    "operation": "clean",
                },
                return_keys=[
                    "dag_run_id: str",
                    "dag_state: str",
                ],
                outputs=OUTPUT,
            )
            START >> orchestrate >> END
        workflow.compile()
        self.clean_document_workflow = workflow

    async def clean(
        self, request: CleanDataRequest, **kwargs
    ):
        """Trigger Airflow DAG to hard-delete Document records marked deleted=True for a given bot."""
        validate_bot(request.bot_id)
        validate_documents_for_clean(request.bot_id, request.ids)
        try:
            import uuid
            request_id = str(uuid.uuid4())
            result = await self.clean_document_workflow.run(
                request_id=request_id,
                inputs={
                    "bot_id": request.bot_id,
                    "ids": request.ids
                }
            )
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Clean document failed: {str(e)}"
            )

    async def upload(self, document: UploadRequest, **kwargs: Any) -> dict[str, Any]:
        validate_bot(document.bot_id)
        validate_active_documents(document.bot_id, document.ids)
        try:
            result = await self.upload_document_workflow.run(
                request_id=str(uuid.uuid4()),
                inputs={"bot_id": document.bot_id, "ids": document.ids},
            )
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upload document failed: {exc}",
            ) from exc

    async def train(self, document: TrainRequest, **kwargs: Any) -> dict[str, Any]:
        validate_bot(document.bot_id)
        validate_documents_for_train(document.bot_id, document.ids)
        try:
            result = await self.train_document_workflow.run(
                request_id=str(uuid.uuid4()),
                inputs={"bot_id": document.bot_id, "ids": document.ids},
            )
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Train document failed: {exc}",
            ) from exc
