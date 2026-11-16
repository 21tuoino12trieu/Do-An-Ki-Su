from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import asyncio
import logging

@dataclass
class Message:
    user_id: str 
    content: str
    timestamp: datetime
    role: str  # 'user' or 'assistant'
    flag: str  # flag for different tasks

@dataclass
class QueueBatch:
    messages: List[Message] = field(default_factory=list)
    is_processing: bool = False
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    processing_batch: List[Message] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # Per-queue lock

class MessageQueueService:
    def __init__(self):
        self.queues: Dict[Tuple[str, str], QueueBatch] = {}
        self._queues_lock = asyncio.Lock()  # Lock only for queue dictionary operations
        self.LOGGER = logging.getLogger(__name__)

    def _get_queue_key(self, user_id: str, flag: str) -> Tuple[str, str]:
        return (user_id, flag)

    async def _get_or_create_queue(self, user_id: str, flag: str) -> QueueBatch:
        queue_key = self._get_queue_key(user_id, flag)
        queue = self.queues.get(queue_key)
        
        if not queue:
            async with self._queues_lock:  # Only lock when modifying queues dict
                queue = self.queues.get(queue_key)
                if not queue:
                    queue = QueueBatch()
                    self.queues[queue_key] = queue
                    self.LOGGER.debug(f"Created new queue for user {user_id} with flag {flag}")
        return queue

    async def add_message(self, message: Message) -> None:
        queue = await self._get_or_create_queue(message.user_id, message.flag)
        
        async with queue.lock:  # Use queue-specific lock
            queue.messages.append(message)
            queue_size = len(queue.messages)
            
        self.LOGGER.info(f"Added message for user {message.user_id} with flag '{message.flag}'. Queue size: {queue_size}")

    async def get_queue_status(self, user_id: str, flag: str) -> dict:
        queue = await self._get_or_create_queue(user_id, flag)
        
        async with queue.lock:  # Use queue-specific lock
            return {
                "pending_count": len(queue.messages),
                "is_processing": queue.is_processing,
                "last_error": queue.last_error,
                "last_error_time": queue.last_error_time
            }

    async def get_batch_for_processing(self, user_id: str, flag: str, min_size: int) -> Optional[List[Message]]:
        """Get all messages in queue if size >= min_size"""
        if min_size < 0:
            raise ValueError("min_size must be positive")
            
        queue = await self._get_or_create_queue(user_id, flag)
        
        async with queue.lock:  # Use queue-specific lock
            if queue.is_processing:
                self.LOGGER.debug(f"Queue for user {user_id} with flag {flag} is already processing")
                return []
                
            current_size = len(queue.messages)
            if current_size < min_size:
                self.LOGGER.debug(f"Queue size {current_size} < min_size {min_size} for user {user_id} with flag {flag}")
                return []

            queue.is_processing = True
            queue.processing_batch = queue.messages.copy()  # Create a copy to avoid reference issues
            messages_to_process = queue.messages.copy()
            queue.messages = []

        self.LOGGER.info(f"Got {current_size} messages for processing for user {user_id} with flag '{flag}'")
        return messages_to_process

    async def mark_batch_processed(self, user_id: str, flag: str) -> None:
        queue = await self._get_or_create_queue(user_id, flag)
        
        async with queue.lock:  # Use queue-specific lock
            queue.processing_batch = []
            queue.is_processing = False
            queue.last_error = None
            queue.last_error_time = None
            
        self.LOGGER.info(f"Batch processed successfully for user {user_id} with flag {flag}")

    async def handle_processing_failure(self, user_id: str, flag: str, error_type: str) -> None:
        queue = await self._get_or_create_queue(user_id, flag)
        
        async with queue.lock:  # Use queue-specific lock
            queue.last_error = error_type
            queue.last_error_time = datetime.now()
            
            if queue.processing_batch:
                # Add failed messages back to the front of the queue
                queue.messages = queue.processing_batch + queue.messages
            
            queue.processing_batch = []
            queue.is_processing = False
            
        self.LOGGER.error(f"Processing failed for user {user_id} with flag {flag}. Error: {error_type}.")
        
    
    async def get_all_queues_stats(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        stats = {}
        
        async with self._queues_lock:
            queue_keys = list(self.queues.keys())
            
        for queue_key in queue_keys:
            queue = self.queues.get(queue_key)
            if queue:
                async with queue.lock:
                    stats[queue_key] = {
                        "message_count": len(queue.messages),
                        "is_processing": queue.is_processing
                    }
                    
        return stats