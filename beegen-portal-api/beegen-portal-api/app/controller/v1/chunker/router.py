import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from beedoc_v3.engine import BeedocEngine

from app.service.chunk import chunk
from app.utils.enums import ChunkingType

router = APIRouter()


@lru_cache()
def get_beedoc_engine() -> BeedocEngine:
    return BeedocEngine()


@router.post("/chunk")
async def process_chunk(
    file: UploadFile = File(...),
    chunk_type: ChunkingType = ChunkingType.HIERARCHICAL,
    beedoc: BeedocEngine = Depends(get_beedoc_engine),
):
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix
    with tempfile.NamedTemporaryFile(delete=False, dir=tmp_dir, suffix=suffix) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        temp_path = tmp_file.name

    try:
        document = await beedoc.process(temp_path)
        reconstructed = (
            document.reconstructed_content or "").strip() if document else ""
        file_name = Path(file.filename or "").name
        zones = []
        if not reconstructed and document:
            for page in document.pages or []:
                sheet_name = page.metadata.get("sheet_name", "") if page.metadata else ""
                for zone in page.content or []:
                    if zone and zone.content:
                        zones.append({"content": zone.content, "sheet_name": sheet_name})

        result = await chunk(
            reconstructed=reconstructed,
            zones=zones,
            file_name=file_name,
            chunk_type=chunk_type,
        )
        return result
    finally:
        # missing_ok: a raise in `finally` would replace whatever exception the
        # body was already propagating, turning a real chunking error into a
        # misleading FileNotFoundError.
        Path(temp_path).unlink(missing_ok=True)
