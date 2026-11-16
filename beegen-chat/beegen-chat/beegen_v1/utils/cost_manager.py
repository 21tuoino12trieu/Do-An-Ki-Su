import re
from typing import NamedTuple

from pydantic import BaseModel

from beegen_v1.loggings import LOGGER


TOKEN_COSTS = {
    "gpt-4o": {"prompt": 1.25, "completion": 5},
    "gpt-4o-2024-05-13": {"prompt": 2.5, "completion": 7.5}
}


class Costs(NamedTuple):
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost: float
    total_budget: float
    
    
class CostManager(BaseModel):
    """Calculate the overhead of using the iterface"""
    
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_budget: float = 0
    max_budget: float = 10.0
    total_cost: float = 0
    token_costs: dict[str, dict[str, float]] = TOKEN_COSTS
    
    
    def update_cost(self, prompt_tokens, completion_tokens, model):
        """
        Update the total cost, prompt tokens, and completion tokens.

        Args:
        prompt_tokens (int): The number of tokens used in the prompt.
        completion_tokens (int): The number of tokens used in the completion.
        model (str): The model used for the API call.
        """
        if prompt_tokens + completion_tokens == 0 or not model:
            return
        
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        
        if model not in self.token_costs:
            LOGGER.warning(f"Model {model} not found in TOKEN_COSTS.")
            return
        
        cost = (
            prompt_tokens * self.token_costs[model]['prompt'] + 
            completion_tokens * self.token_costs[model]["completion"]
        ) / 1000
        
        self.total_cost += cost
        LOGGER.info(
            f"Total running cost: ${self.total_cost:.3f} | Max budget: ${self.max_budget:.3f} | "
            f"Current cost: ${cost:.3f}, prompt_tokens: {prompt_tokens}, completion_tokens: {completion_tokens}"
        )

    def get_costs(self) -> Costs:
        """Get all costs"""
        return Costs(self.total_prompt_tokens, self.total_completion_tokens, self.total_cost, self.total_budget)
    
    
class TokenCostManager(CostManager):
    """open llm model is self-host, it's free and without cost"""

    def update_cost(self, prompt_tokens, completion_tokens, model):
        """
        Update the total cost, prompt tokens, and completion tokens.

        Args:
        prompt_tokens (int): The number of tokens used in the prompt.
        completion_tokens (int): The number of tokens used in the completion.
        model (str): The model used for the API call.
        """
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        LOGGER.info("prompt_tokens: %s, completion_tokens: %s", prompt_tokens, completion_tokens)