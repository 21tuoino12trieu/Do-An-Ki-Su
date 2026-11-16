from fastapi import APIRouter, Depends

from app.auth.middleware import verify_token
from app.controller.v1.portal.router import router as portal_router
from app.controller.v1.chunker.router import router as chunker_router
from app.controller.v1.portal.document_ingestion_router import (
    router as document_ingestion_router,
)

router = APIRouter(
    prefix="/portal",
    dependencies=[Depends(verify_token)],
)

router.include_router(
    portal_router,
    tags=["Portal"],
)
router.include_router(
    chunker_router,
    tags=["Chunker"],
)
router.include_router(
    document_ingestion_router,
    tags=["Document Ingestion"],
)
