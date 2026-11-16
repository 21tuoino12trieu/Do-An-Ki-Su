from typing import List
from typing_extensions import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.utils.enums import DocumentType


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UploadRequest(BaseModel):
    bot_id: NonEmptyStr
    type: DocumentType
    ids: List[NonEmptyStr] = Field(..., min_length=1)

class UploadJobRequest(BaseModel):
    bot_id: NonEmptyStr
    type: DocumentType
    id: NonEmptyStr

class TrainRequest(BaseModel):
    bot_id: NonEmptyStr
    ids: List[NonEmptyStr] = Field(..., min_length=1)
    type: DocumentType

class TrainJobRequest(BaseModel):
    bot_id: NonEmptyStr
    id: NonEmptyStr

class UpdateDocumentRequest(BaseModel):
    bot_id: NonEmptyStr
    type: DocumentType
    ids: List[NonEmptyStr] = Field(..., min_length=1)

class UpdateChunkRequest(BaseModel):
    document_id: NonEmptyStr

class RevertDataRequest(BaseModel):
    bot_id: NonEmptyStr

class CleanDataRequest(BaseModel):
    bot_id: NonEmptyStr
    type: DocumentType
    ids: List[NonEmptyStr] = Field(..., min_length=1)

class CleanJobRequest(BaseModel):
    bot_id: NonEmptyStr
    type: DocumentType
    id: NonEmptyStr

class ConvertFormatRequest(BaseModel):
    doc_id: NonEmptyStr

class CreateBotRequest(BaseModel):
    bot_id: NonEmptyStr

class DeleteBotRequest(BaseModel):
    bot_id: NonEmptyStr
