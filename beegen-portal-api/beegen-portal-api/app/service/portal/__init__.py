from app.service.portal.process_document import ProcessDocumentService

process_document_service = ProcessDocumentService()

# TAM THOI TAT: ProcessQnAService/ProcessBotService khoi tao MilvusNode ngay
# luc import, va Milvus server dev hien khong ket noi duoc tu may local.
# Bat lai bang cach uncomment 2 dong duoi + 2 import o tren khi Milvus da on.
from app.service.portal.process_qna import ProcessQnAService
from app.service.portal.process_bot import ProcessBotService
process_qna_service = ProcessQnAService()
process_bot_service = ProcessBotService()
# process_qna_service = None
# process_bot_service = None