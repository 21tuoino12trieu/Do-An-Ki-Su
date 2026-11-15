from beeflow.states.workflow_state import WorkflowState
from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.loggings import LOGGER
from beegen.utils.common import extract_condition_variables
from typing import Dict, Any, Optional, List


class BranchNodeConfig(NodeConfig):
    """Configuration for a branching node in the workflow."""
    type: NodeType = "branch"
    
    cases: Dict[str, str] = {}  # Mapping from condition to target node id
    default_target: Optional[str] = None  # Default node ID if no conditions match
    candidate_list: Optional[List[str]] = None


class BranchNode(BaseNode):
    """A node that evaluates conditions and routes flow to different target nodes."""
    
    type: NodeType = "branch"
    
    output_schema: ParamSet = (
        ParamSet.new()
            .var("target: str", required=True)
            .var("matched: str")
            .build()
    )
    
    __slots__ = [
        'given_candidates',     # List of all possible target nodes
        'conditions',     # List of (compiled_code, condition_string, target) tuples
        'default', # Default target if no conditions match
        'cases',          # Original cases mapping
    ]
    
    def __init__(
        self, 
        cases: Optional[Dict[str, str]] = None,
        candidates: Optional[List[str]] = None,
        default: Optional[str] = None,
        **kwargs
    ):
        """Initialize BranchNode from either config or kwargs.
        
        Args:
            config: Optional BranchNodeConfig object. If provided, other args are ignored.
            name: Node name (required if config not provided)
            cases: Dictionary mapping conditions to target node names
            default_target: Default target node if no conditions match
            **kwargs: Additional keyword arguments for NodeConfig
        """        
        
        super().__init__(**kwargs)
        
        # Initialize from config
        self.cases = cases
        
        for key, value in self.cases.items():
            if hasattr(value, 'is_base_node'):
                self.cases[key] = value.name
        
        self.default = default.name if hasattr(default, 'is_base_node') else default
        self.given_candidates = candidates
        
        self._build_schema()
        
        # Precompile conditions for performance
        self.conditions = self._compile_conditions()
        
        # Set up core evaluation function
        self.core = self._create_core_function()
                
    def _build_schema(self):
        input_schema = ParamSet.new().var("anchor: str = None")
        
        for condition in self.cases:
            vars = extract_condition_variables(condition)
            for k, v in vars.items():
                input_schema = input_schema.var(f"{k}: {v}", required=True)
        
        self.input_schema = input_schema.build()
        
    @property
    def candidates(self) -> List[str]:
        if self.given_candidates:
            return self.given_candidates
            
        """Returns all target node IDs defined in the cases mapping."""
        if self.default:
            return list(self.cases.values()) + [self.default]
        else:
            return list(self.cases.values())
    
    def _compile_conditions(self) -> List[tuple]:
        """Precompile all conditions for maximum performance."""
        compiled_conditions = []
        
        for condition, target in self.cases.items():
            try:
                # Compile each condition into a code object once
                compiled_code = compile(condition, f'<condition: {condition}>', 'eval')
                compiled_conditions.append((compiled_code, condition, target))
            except SyntaxError as e:
                LOGGER.error(f"Invalid condition syntax '{condition}': {e}")
                raise ValueError(f"Invalid condition syntax: {condition}")
        
        return compiled_conditions
    
    def _create_core_function(self):
        """Create the optimized core evaluation function."""
        def core(**inputs) -> Dict[str, str]:
            # Priority 1: Check for anchor (direct routing)
            anchor = inputs.get('anchor')
            if anchor:
                # if anchor in self.candidates:
                return {"target": anchor, "matched": "anchor"}
                # else:
                #     LOGGER.warning(f"Anchor '{anchor}' not in candidates: {self.candidates}")
            
            # Priority 2: Evaluate conditions
            target, matched = self._evaluate_conditions(inputs)
            return {"target": target, "matched": matched}
        
        return core
    
    def _evaluate_conditions(self, inputs: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """Evaluate all conditions and return the first match."""
        # Create a safe copy of inputs to prevent mutation issues
        safe_inputs = dict(inputs)
        
        # Check each compiled condition
        for compiled_cond, condition_str, target in self.conditions:
            try:
                # Using compiled code object for performance
                result = eval(compiled_cond, {"__builtins__": {}}, safe_inputs)
                
                if result:
                    LOGGER.debug(f"Condition '{condition_str}' matched, routing to '{target}'")
                    return target, condition_str
                    
            except Exception as e:
                LOGGER.error(f"Error evaluating condition '{condition_str}': {e}")
                continue
        
        # No conditions matched, use default
        if self.default:
            LOGGER.debug(f"No conditions matched, using default target '{self.default}'")
            return self.default, "default"
        else:
            LOGGER.warning("No conditions matched and no default target specified")
            return None, None
    
    def get_target(
        self, 
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Optional[str]:
        return state[self.full_name, "target", context_id]
    
    def specific_metadata(self) -> Dict[str, Any]:
        """Return subclass-specific metadata dictionary."""
        return {
            "cases": self.cases,
            "default_target": self.default,
            "candidates": self.candidates,
            "num_conditions": len(self.conditions)
        }




