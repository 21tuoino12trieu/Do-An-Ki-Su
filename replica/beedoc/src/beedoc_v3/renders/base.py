import uuid
from typing import Any, Optional, TYPE_CHECKING
from beedoc_v3.core.interfaces import IRenderer
from beedoc_v3.core.exceptions import RendererError, WorkflowError

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document
    from beeflow.workflow import WorkflowEngine

class BaseRenderer(IRenderer):
    """
    Lớp renderer nền điều phối bằng Beeflow.
    Renderer HTML chỉ chuyển đổi nội dung, không gọi model.
    """

    def __init__(self, config: Optional[Any] = None):
        self.config: Optional[Any] = config
        self.workflow: Optional["WorkflowEngine"] = None

    def _build_workflow(self) -> "WorkflowEngine":
        """
        Abstract method to be implemented by subclasses.
        Each subclass defines its own Beeflow graph.
        """
        raise NotImplementedError("Subclasses must implement _build_workflow")

    async def render(self, document: 'Document') -> 'Document':
        """Executes the Beeflow workflow for reconstruction."""
        if not self.workflow:
            self.workflow = self._build_workflow()

        if not self.workflow:
            raise WorkflowError(f"Workflow not initialized for {self.__class__.__name__}")

        try:
            results = await self.workflow.run(
                inputs={
                    "document": document,
                    "config": self.config
                },
                request_id=str(uuid.uuid4())
            )
            # The workflow is expected to update the document object directly
            # or return it through a final node.
            return document
        except Exception as e:
            raise RendererError(f"Renderer workflow failed: {str(e)}")
