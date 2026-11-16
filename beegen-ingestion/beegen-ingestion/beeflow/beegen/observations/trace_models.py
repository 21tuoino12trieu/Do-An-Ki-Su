from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from beegen.configs.yaml_model import YamlModel
from pydantic import ConfigDict, field_serializer, field_validator


class BaseTraceInfo(YamlModel):
    """Base class for trace information in workflow and system monitoring.
    
    This class provides a common structure for capturing execution traces,
    including timing information, inputs/outputs, and metadata. It serves as
    the foundation for more specialized trace information classes.
    
    Attributes:
        message_id (Optional[str]): Unique identifier for the associated message.
        message_data (Optional[Any]): Raw data associated with the message.
        inputs (Optional[Union[str, dict[str, Any], list]]): Input data for the traced operation.
            Can be a string, dictionary, or list. Invalid types are converted to empty string.
        outputs (Optional[Union[str, dict[str, Any], list]]): Output data from the traced operation.
            Can be a string, dictionary, or list. Invalid types are converted to empty string.
        start_time (Optional[datetime]): Timestamp when the operation began.
        end_time (Optional[datetime]): Timestamp when the operation completed.
        metadata (dict[str, Any]): Additional key-value pairs for storing custom trace information.
        trace_id (Optional[str]): Unique identifier for this trace instance.
    
    Note:
        DateTime fields are automatically serialized to ISO format strings when the model
        is serialized. The inputs and outputs fields are validated to ensure they are
        of supported types (str, dict, or list).
    """
    message_id: Optional[str] = None
    message_data: Optional[Any] = None
    inputs: Optional[Union[str, dict[str, Any], list]] = None
    outputs: Optional[Union[str, dict[str, Any], list]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: dict[str, Any]
    trace_id: Optional[str] = None

    @field_validator("inputs", "outputs")
    @classmethod
    def ensure_type(cls, v):
        """Validate and normalize inputs and outputs fields.
        
        Ensures that inputs and outputs are of supported types (str, dict, or list).
        If the value is not one of these types, it's converted to an empty string.
        
        Args:
            v: The value to validate.
            
        Returns:
            The validated value or an empty string if the type is not supported.
        """
        if v is None:
            return None
        if isinstance(v, str | dict | list):
            return v
        return ""

    model_config = ConfigDict(protected_namespaces=())

    @field_serializer("start_time", "end_time")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize datetime fields to ISO format strings.
        
        Converts datetime objects to ISO 8601 formatted strings for JSON serialization.
        
        Args:
            dt (datetime | None): The datetime object to serialize.
            
        Returns:
            str | None: ISO formatted datetime string or None if input is None.
        """
        if dt is None:
            return None
        return dt.isoformat()


class WorkflowTraceInfo(BaseTraceInfo):
    """Extended trace information specifically for workflow execution monitoring.
    
    This class extends BaseTraceInfo with workflow-specific fields to capture
    comprehensive information about workflow runs, including performance metrics,
    execution status, and workflow-specific identifiers.
    
    Inherits all attributes from BaseTraceInfo and adds workflow-specific fields:
    
    Attributes:
        workflow_data (Any): Raw workflow configuration or execution data.
        conversation_id (Optional[str]): Identifier linking this workflow to a conversation context.
        workflow_app_log_id (Optional[str]): Application-level log identifier for this workflow execution.
        workflow_id (str): Unique identifier for the workflow definition/template.
        tenant_id (str): Identifier for the tenant/organization running the workflow.
        workflow_run_id (str): Unique identifier for this specific workflow execution instance.
        workflow_run_elapsed_time (Union[int, float]): Total execution time in seconds.
        workflow_run_status (str): Current status of the workflow run (e.g., 'completed', 'failed', 'running').
        workflow_run_inputs (Mapping[str, Any]): Input parameters provided to the workflow run.
        workflow_run_outputs (Mapping[str, Any]): Output values produced by the workflow run.
        workflow_run_version (str): Version identifier of the workflow that was executed.
        error (Optional[str]): Error message if the workflow execution failed.
        total_tokens (int): Total number of tokens consumed during workflow execution.
        file_list (list[str]): List of files processed or generated during workflow execution.
        query (str): The original query or prompt that initiated the workflow.
        metadata (dict[str, Any]): Additional workflow-specific metadata (inherited from BaseTraceInfo).
    
    Example:
        ```python
        workflow_trace = WorkflowTraceInfo(
            workflow_id="text-processing-v1",
            tenant_id="org-123",
            workflow_run_id="run-456",
            workflow_run_elapsed_time=2.5,
            workflow_run_status="completed",
            workflow_run_inputs={"text": "Hello world"},
            workflow_run_outputs={"processed_text": "HELLO WORLD"},
            workflow_run_version="1.2.0",
            total_tokens=150,
            file_list=["input.txt", "output.txt"],
            query="Convert text to uppercase",
            metadata={"priority": "high"}
        )
        ```
    
    Note:
        This class is designed for comprehensive workflow monitoring and analytics.
        All timing and token usage information can be used for performance optimization
        and cost tracking.
    """
    workflow_data: Any
    conversation_id: Optional[str] = None
    workflow_app_log_id: Optional[str] = None
    workflow_id: str
    tenant_id: str
    workflow_run_id: str
    workflow_run_elapsed_time: Union[int, float]
    workflow_run_status: str
    workflow_run_inputs: Mapping[str, Any]
    workflow_run_outputs: Mapping[str, Any]
    workflow_run_version: str
    error: Optional[str] = None
    total_tokens: int
    file_list: list[str]
    query: str
    metadata: dict[str, Any]
    
    
class MessageTraceInfo(BaseTraceInfo):
    """Trace information specifically for individual message processing and conversation tracking.
    
    This class extends BaseTraceInfo to capture detailed information about message-level
    operations within conversations, including token usage, model information, and
    file handling. It's designed for monitoring conversational AI interactions.
    
    Inherits all attributes from BaseTraceInfo and adds message-specific fields:
    
    Attributes:
        conversation_model (str): The AI model used for processing this message 
            (e.g., "gpt-4", "claude-3", "llama-2").
        message_tokens (int): Number of tokens in the input message/prompt.
        answer_tokens (int): Number of tokens generated in the response/answer.
        total_tokens (int): Total token count for the entire message exchange 
            (typically message_tokens + answer_tokens + any system tokens).
        error (Optional[str]): Error message if the message processing failed or encountered issues.
        file_list (Optional[Union[str, dict[str, Any], list]]): Files associated with this message.
            Can be a single filename (str), file metadata (dict), or list of files.
            Subject to the same validation as inputs/outputs in BaseTraceInfo.
        message_file_data (Optional[Any]): Raw file data or metadata associated with 
            files processed in this message.
        conversation_mode (str): The mode or type of conversation (e.g., "chat", "completion", 
            "assistant", "function_calling").
    
    Example:
        ```python
        message_trace = MessageTraceInfo(
            message_id="msg-789",
            conversation_model="claude-3-sonnet",
            message_tokens=45,
            answer_tokens=120,
            total_tokens=165,
            conversation_mode="chat",
            file_list=["document.pdf", "image.jpg"],
            inputs="What's in these files?",
            outputs="The PDF contains a research paper and the image shows a chart.",
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(seconds=3),
            metadata={"user_id": "user-123", "session_id": "session-456"}
        )
        ```
    
    Note:
        This class is particularly useful for:
        - Token usage tracking and billing
        - Performance monitoring of message processing
        - File handling auditing in conversational contexts
        - Debugging conversation flows and model behavior
        
        The file_list field uses the same validation as inputs/outputs,
        ensuring type safety and consistency.
    """
    conversation_model: str
    message_tokens: int
    answer_tokens: int
    total_tokens: int
    error: Optional[str] = None
    file_list: Optional[Union[str, dict[str, Any], list]] = None
    message_file_data: Optional[Any] = None
    conversation_mode: str
    trace_id: Optional[str] = None