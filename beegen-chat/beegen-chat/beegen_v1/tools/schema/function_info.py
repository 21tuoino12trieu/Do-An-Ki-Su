from .param import Param, ParamSet
from beegen_v1.configs.yaml_model import YamlModel
from typing import Optional, Dict, Any


class FunctionInfo(YamlModel):
    """Model representing parsed function metadata."""
    
    name: str
    input_schema: Optional[ParamSet] = None
    output_schema: Optional[ParamSet] = None
    description: Optional[str] = None
    source: Optional[str] = None
    
    @classmethod
    def from_parsed_data(cls, data: Dict[str, Any]) -> 'FunctionInfo':
        """Create FunctionInfo from parser output."""
        param_set = ParamSet.new()
        
        for name, info in data.get('inputs', {}).items():
            param = Param(
                type=info['type'],
                required=info['required'],
                default=info['default'],
                description=info['description']
            )
            param_set.add_param(name, param)
        
        return cls(
            name=data['name'],
            param_set=param_set.build(),
            return_info=data.get('outputs'),
            description=data.get('description')
        )