from abc import ABC, abstractmethod
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam


# Abstract method base on openai-agents-python example
class BaseAgent(ABC):
    @abstractmethod
    def run(messages: list[ChatCompletionMessageParam]):
        """Stream completion."""
        pass
