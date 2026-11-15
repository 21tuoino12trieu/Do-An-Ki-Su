from typing import Optional, Dict, List, Any, Set
import os
import asyncio
from dataclasses import dataclass
from langfuse import Langfuse
from beegen.configs import LangfuseConfig


@dataclass
class TraceItem:
    """Represents a single trace item (span, generation, or event)."""
    type: str  # "span", "generation", "event"
    parent: Optional[str]  # Parent item name, None for root
    data: Dict[str, Any]  # Item-specific data (excluding trace metadata)
    trace_metadata: Dict[str, Any]  # Trace-level metadata (user_id, session_id, etc.)
    

class AsyncTraceBuffer:
    """
    An async buffer for collecting hierarchical traces, spans, events, and generations
    before flushing them to Langfuse.
    
    Uses parent-child relationships with simple name-based keys for clean hierarchy management.
    Separates trace-level metadata (user_id, session_id, request_id) from item data.
    """
    
    # Trace-level metadata keys that should be handled separately
    TRACE_METADATA_KEYS = {"user_id", "session_id", "request_id", "tags", "metadata", "release", "version"}
    
    def __init__(
        self,
        config: Optional[LangfuseConfig] = None,
        langfuse_client: Optional[Langfuse] = None
    ):
        """
        Initialize AsyncTraceBuffer.
        
        Args:
            config: LangfuseConfig object for creating a new Langfuse client
            langfuse_client: Existing Langfuse client instance
        """
        self._client = self._initialize_client(config, langfuse_client)
        # Structure: {request_id: {item_name: TraceItem}}
        self._buffer: Dict[str, Dict[str, TraceItem]] = {}
        self._lock = asyncio.Lock()
        
    def _initialize_client(
        self, 
        config: Optional[LangfuseConfig], 
        langfuse_client: Optional[Langfuse]
    ) -> Langfuse:
        """Initialize and validate Langfuse client."""
        if langfuse_client:
            client = langfuse_client
        elif config:
            client = Langfuse(
                public_key=config.public_key,
                secret_key=config.secret_key,
                host=config.host
            )
        else:
            raise ValueError("Either config or langfuse_client must be provided")
        
        client.auth_check()
        return client
    
    def _separate_trace_metadata(self, kwargs: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Separate trace-level metadata from item data.
        
        Args:
            kwargs: Combined parameters
            
        Returns:
            Tuple of (item_data, trace_metadata)
        """
        item_data = {}
        trace_metadata = {}
        
        for key, value in kwargs.items():
            if key in self.TRACE_METADATA_KEYS:
                trace_metadata[key] = value
            else:
                item_data[key] = value
                
        return item_data, trace_metadata
    
    def add_span(
        self, 
        request_id: str, 
        name: str,
        parent: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Add a span to the buffer.
        
        Args:
            request_id: Unique identifier for the request
            name: Unique name of the span within the request
            parent: Name of parent span/generation, None for root
            **kwargs: Span parameters including trace metadata (user_id, session_id, etc.)
                     and item data (input, output, tags, etc.)
        """
        item_data, trace_metadata = self._separate_trace_metadata(kwargs)
        self._add_item(request_id, name, "span", parent, item_data, trace_metadata)
    
    def add_generation(
        self,
        request_id: str,
        name: str,
        parent: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Add a generation to the buffer.
        
        Args:
            request_id: Unique identifier for the request
            name: Unique name of the generation within the request
            parent: Name of parent span/generation, None for root
            model: Model name (e.g., "gpt-4o")
            **kwargs: Generation parameters including trace metadata (user_id, session_id, etc.)
                     and item data (input, output, model_parameters, usage_details, etc.)
        """
        item_data, trace_metadata = self._separate_trace_metadata(kwargs)
        if model:
            item_data["model"] = model
        
        self._add_item(request_id, name, "generation", parent, item_data, trace_metadata)
    
    def add_event(
        self,
        request_id: str,
        name: str,
        parent: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Add an event to the buffer.
        
        Args:
            request_id: Unique identifier for the request
            name: Unique name of the event within the request
            parent: Name of parent span/generation, None for root
            **kwargs: Event parameters including trace metadata (user_id, session_id, etc.)
                     and item data (level, message, etc.)
        """
        item_data, trace_metadata = self._separate_trace_metadata(kwargs)
        self._add_item(request_id, name, "event", parent, item_data, trace_metadata)
    
    def _add_item(
        self,
        request_id: str,
        name: str,
        item_type: str,
        parent: Optional[str],
        item_data: Dict[str, Any],
        trace_metadata: Dict[str, Any]
    ) -> None:
        """Internal method to add any type of item."""
        if request_id not in self._buffer:
            self._buffer[request_id] = {}
        
        # Ensure name is included in item data
        if "name" not in item_data:
            item_data["name"] = name
        
        self._buffer[request_id][name] = TraceItem(
            type=item_type,
            parent=parent,
            data=item_data,
            trace_metadata=trace_metadata
        )
    
    def update_item(
        self,
        request_id: str,
        name: str,
        **kwargs
    ) -> bool:
        """
        Update an existing item in the buffer.
        
        Args:
            request_id: Unique identifier for the request
            name: Name of the item to update
            **kwargs: Data to update (can include both item data and trace metadata)
            
        Returns:
            True if item was found and updated, False otherwise
        """
        if request_id in self._buffer and name in self._buffer[request_id]:
            item_data, trace_metadata = self._separate_trace_metadata(kwargs)
            
            # Update item data
            self._buffer[request_id][name].data.update(item_data)
            
            # Update trace metadata
            self._buffer[request_id][name].trace_metadata.update(trace_metadata)
            
            return True
        return False
    
    def _build_hierarchy_order(self, items: Dict[str, TraceItem]) -> List[str]:
        """
        Build processing order based on parent-child dependencies.
        Parents must be processed before their children.
        
        Args:
            items: Dictionary of items for a request
            
        Returns:
            List of item names in dependency order
            
        Raises:
            ValueError: If circular dependencies are detected
        """
        # Find all root items (no parent)
        roots = [name for name, item in items.items() if item.parent is None]
        
        if not roots:
            raise ValueError("No root items found - at least one item must have parent=None")
        
        ordered = []
        visited = set()
        visiting = set() # For cycle detection
        
        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving '{name}'")
            if name in visited:
                return
            if name not in items:
                raise ValueError(f"Parent '{name}' referenced but not found in items")
            
            visiting.add(name)
            
            # Visit all children of this item
            children = [child_name for child_name, child_item in items.items()
                        if child_item.parent == name]
            
            for child in children:
                visit(child)
            
            visiting.remove(name)
            visited.add(name)
            ordered.append(name)
        
        # Process all roots and their descendants
        for root in roots:
            visit(root)
            
        # Ensure all items were processed
        unprocessed = set(items.keys()) - visited
        if unprocessed:
            raise ValueError(f"Orphaned items detected (no path from root): {unprocessed}")
        
        # Reverse to get parents-first order
        return ordered[::-1]    

    def clear_request(self, request_id: str) -> bool:
        """
        Clear all data for a specific request without flushing.
        
        Args:
            request_id: Request ID to clear
            
        Returns:
            True if request was found and cleared, False otherwise
        """
        if request_id in self._buffer:
            del self._buffer[request_id]
            return True
        return False
            
    async def flush(self, request_id: str) -> bool:
        """
        Flush all buffered items for a request to Langfuse and remove from buffer.
        
        Args:
            request_id: Request ID to flush
            
        Returns:
            True if request was found and flushed, False if request not found
            
        Raises:
            ValueError: If hierarchy validation fails
            Exception: If Langfuse operations fail
        """
        async with self._lock:
            if request_id not in self._buffer:
                return False
            
            items = self._buffer[request_id].copy()
                        
            # Validate and get processing order
            try:
                ordered_names = self._build_hierarchy_order(items)
            except ValueError as e:
                raise ValueError(f"Cannot flush request {request_id}: {e}")
            
            # Track created Langfuse objects for parent-child linking
            langfuse_objects = {}  # name -> langfuse object
            
            try:
                for name in ordered_names:
                    item = items[name]
                    
                    if item.type == "span":
                        langfuse_obj = self._create_span(item, langfuse_objects)
                    elif item.type == "generation":
                        langfuse_obj = self._create_generation(item, langfuse_objects)
                    else:
                        raise ValueError(f"Unknown item type: {item.type}")
                    
                    # Update trace metadata after creation
                    if item.trace_metadata:
                        langfuse_obj.update_trace(**item.trace_metadata)
                    
                    langfuse_objects[name] = langfuse_obj
                
                # End all spans and generations (events don't need ending)
                for name in reversed(ordered_names):  # End in reverse order (children first)
                    item = items[name]
                    langfuse_obj = langfuse_objects[name]
                    
                    if item.type in ["span", "generation"] and hasattr(langfuse_obj, 'end'):
                        langfuse_obj.end()
                
                # Remove from buffer after successful flush
                self._client.flush()
                del self._buffer[request_id]
                return True
                
            except Exception as e:
                import traceback
                # If flush fails, keep items in buffer for potential retry
                raise Exception(f"Failed to flush request {request_id} to Langfuse: {traceback.format_exc()}")

    def _create_span(self, item: TraceItem, langfuse_objects: Dict[str, Any]) -> Any:
        """Create a Langfuse span from TraceItem."""
        data = item.data.copy()
        name = data.pop("name", "unnamed-span")
        
        # Get parent object if exists
        parent_obj = None
        if item.parent and item.parent in langfuse_objects:
            parent_obj = langfuse_objects[item.parent]
        
        if parent_obj:
            span = parent_obj.span(name=name, **data)
        else:
            # Root span
            span = self._client.span(name=name, **data)
        
        return span

    def _create_generation(self, item: TraceItem, langfuse_objects: Dict[str, Any]) -> Any:
        """Create a Langfuse generation from TraceItem."""
        data = item.data.copy()
        name = data.pop("name", "unnamed-generation")
        
        # Get parent object if exists
        parent_obj = None
        if item.parent and item.parent in langfuse_objects:
            parent_obj = langfuse_objects[item.parent]
        
        if parent_obj:
            generation = parent_obj.generation(name=name, **data)
        else:
            # Root generation
            generation = self._client.generation(name=name, **data)
        
        return generation

    async def flush_all(self) -> Dict[str, bool]:
        """
        Flush all buffered requests to Langfuse.
        
        Returns:
            Dictionary mapping request_id -> success status
        """
        results = {}
        
        async with self._lock:
            request_ids = list(self._buffer.keys())
        
        for request_id in request_ids:
            try:
                results[request_id] = await self.flush(request_id)
            except Exception as e:
                print(f"Failed to flush request {request_id}: {e}")
                results[request_id] = False
        
        return results


async def main():
    """Example demonstrating the AsyncTraceBuffer usage with separated trace metadata."""
    
    # Initialize the buffer
    trace_buffer = AsyncTraceBuffer(
        config=LangfuseConfig(
            public_key="pk-lf-93d8aa5d-424b-4e31-96f3-d09fc5b2b24f",
            secret_key="sk-lf-fd1619a2-fd78-4060-b49b-58b0476f1be6",
            host="http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn",
            no_proxy="*.mbbank.com.vn"
        )
    )
    
    request_id = "request_123"
    
    # Build hierarchy: root -> joke-gen -> validation
    
    # 1. Add root span with trace metadata separated
    trace_buffer.add_span(
        request_id=request_id,
        name="root",
        parent=None,  # Root level
        input={"user_query": "Tell me a joke about OpenTelemetry"},
        # Trace metadata (will be separated automatically)
        user_id="user_123",
        session_id="session_abc",
        tags=["experimental", "comedy"],
        metadata={"environment": "production"}
    )
    
    # 2. Add generation under root
    trace_buffer.add_generation(
        request_id=request_id,
        name="joke-gen",
        parent="root",  # Child of root
        model="gpt-4o",
        input=[{"role": "user", "content": "Tell me a joke about OpenTelemetry"}],
        metadata={"temperature": 0.7},
        # Trace metadata
        user_id="user_123",  # Will be handled via update_trace
        session_id="session_abc"
    )
    
    # 3. Add event under generation
    trace_buffer.add_span(
        request_id=request_id,
        name="validation",
        parent="root",
        input={"user_query": "Tell me a joke about OpenTelemetry"},
        # Trace metadata (will be separated automatically)
        user_id="user_123",
        session_id="session_abc",
        tags=["experimental", "comedy"],
        metadata={"environment": "production"}
    )
    
    # 4. Update items with results (including both item data and trace metadata)
    trace_buffer.update_item(
        request_id=request_id,
        name="joke-gen",
        output="Why did the OpenTelemetry collector break up with the span? Because it needed more space... for its attributes!",
        usage_details={"input_tokens": 10, "output_tokens": 25},
        # Can also update trace metadata
        version="1.2.3"
    )
    
    trace_buffer.update_item(
        request_id=request_id,
        name="root",
        output={"final_joke": "Why did the OpenTelemetry collector break up with the span? Because it needed more space... for its attributes!"}
    )
    
    # Flush all to Langfuse
    asyncio.create_task(trace_buffer.flush("request_123"))
    
    await asyncio.sleep(3)
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())