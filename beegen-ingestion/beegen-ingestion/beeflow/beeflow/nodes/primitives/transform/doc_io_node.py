from beedoc.processor import DocumentProcessingPipeline
from beeflow.configs import NodeConfig, NodeType
from beeflow.nodes import BaseNode
from beegen.tools.schema.param import ParamSet
from beedoc.core.entities import OutputFormat, DocumentType, ProcessingConfig
from typing import Dict, Callable, Any, Union, Optional, List
from pydantic import model_validator


class DocumentIONodeConfig(NodeConfig):
    """Configuration for node that use to process, transform documents."""
    type: NodeType = "doc-processor"
    
    max_dimension: int = 1200
    quality: int = 85
    document_type: DocumentType = DocumentType.PDF
    output_format: OutputFormat = OutputFormat.TEXT
    

class DocumentIONode(BaseNode):
    """
    Node converts input document (e.g., PDF, DOCX, images)
    into image or text representations (e.g., NumPy arrays or base64 strings) for downstream processing in a workflow.
    """
    
    type: NodeType = "doc-processor"
    
    __slots__ = [
        "output_format",
        "document_type",
        "max_dimension",
        "quality",
        "backend"
    ]
    
    input_schema: ParamSet = (
        ParamSet.new()
            .var(
                "path: str",
                required=True,
                description=(
                    "Path to the document file to convert. This should be a valid file path "
                    "pointing to the document location on the filesystem.\n\n"
                    "Supported formats:\n"
                    "- PDF files (.pdf)\n"
                    "- Image files (.jpg, .jpeg, .png, .bmp, .tiff, etc.)"
                )
            )
            .var(
                "data: bytes",
                required=False,
                description=(
                    "Raw document data as bytes. Use this when you have the document content "
                    "loaded in memory (e.g., from an uploaded file stream, API response, or "
                    "when reading from a non-filesystem source).\n\n"
                    "If provided, this takes precedence over the 'path' parameter. "
                    "The data should contain the complete document content in one of the "
                    "supported formats (PDF, JPEG, PNG, etc.)."
                )
            )
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("document_name: str")
            .var("document_type: str", description="'image' or 'pdf'")
            .var("document_path: str")
            .var("total_pages: Optional[int]")
            .var("pages: Optional[List[Dict[str, Any]]]")
            .build()
    )
    
    def __init__(
        self,
        document_type: Optional[DocumentType] = None,
        output_format: Optional[OutputFormat] = None,
        max_dimension: Optional[int] = None,
        quality: Optional[int] = None,
        **kwargs
    ):
        self.document_type = document_type or DocumentType.PDF
        self.output_format = output_format or OutputFormat.TEXT
        self.max_dimension = max_dimension or 1200
        self.quality = quality or 85
        
        super().__init__(**kwargs)
        
        self.backend = DocumentProcessingPipeline(
            config=ProcessingConfig(
                output_format=self.output_format,
                max_dimension=self.max_dimension,
                quality=self.quality
            )
        )
        
        self.core = self._process
    
    async def _process(self, path: str, data: Optional[bytes] = None) -> Dict[str, Any]:
        if data is not None:
            result = await self.backend.process_from_bytes(
                name=path,
                content=data,
                document_type=self.document_type
            )
        else:
            result = await self.backend.process_from_path(path)
            
        return {
            "document_name": result.document_name,
            "document_type": result.document_type.value,
            "document_path": path,
            "total_pages": result.total_pages,
            "pages": [
                {
                    "page_number": page.page_number,
                    "image_data": page.image_data,
                    "text_data": page.text_data,
                    "width": page.width,
                    "height": page.height
                }
                for page in result.pages
            ]
        }
        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return node-specific metadata for logging/debugging."""
        return {
            "max_dimension": self.max_dimension,
            "quality": self.quality,
            "document_type": self.document_type,
            "output_format": self.output_format
        }
        

async def main():
    
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    doc_io_node = DocumentIONode(
        name="doc0",
        document_type="pdf",
        output_format="base64",
        inputs={"data": INPUT, "path": INPUT},
        quality=90,
        outputs=OUTPUT
    )
    
    indexer = WorkflowIndexer(name="workflow01")\
        .add_node(doc_io_node).build()
    
    document_local_path = r"D:\work\beeflow\data\sample2.pdf"
    # document_path = "data/sample2.pdf"  # (local)

    with open(document_local_path, "rb") as f:
        file_bytes = f.read()
    
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "path": document_local_path,
            "data": file_bytes
        }
    )
    
    async for chunk in doc_io_node.run(state=state):
        pass
    
    print(doc_io_node.get_outputs(state))
    
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())