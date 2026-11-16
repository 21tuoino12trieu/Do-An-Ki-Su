from abc import ABC, abstractmethod
from typing import Any, Union, List


class BaseEmbedder(ABC):
    r"""Abstract base class for text embedding functionalities."""
    
    @abstractmethod
    async def run(
        self,
        texts: Union[str, List[str]],
        **kwargs: Any
    ) -> List[List[float]]:
        """
        Abstract method for embedding a list of text strings into a list of numerical vectors.

        Parameters:
            texts (list[str]): A list of text strings to be embedded.
            **kwargs (Any): Extra kwargs passed to the embedding API.

        Returns:
            list[list[float]]: A list that represents the
                generated embedding as a list of floating-point numbers.
        """
        pass
    
    @abstractmethod
    def get_output_dim(self) -> int:
        r"""Returns the output dimension of the embeddings.
        
        Returns:
            int: The dimensionality of the embeddings for the current model.
        """
        pass