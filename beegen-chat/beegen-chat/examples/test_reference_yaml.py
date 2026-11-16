from beegenerate.configs.yaml_model import YamlModel


from pydantic import model_validator
from typing import Optional

class Reference(YamlModel):
    id: Optional[str] = None
    field: Optional[str] = None
    value: Optional[str] = None
    
    @model_validator(mode="before")
    def validate_reference(cls, values):
        value = values.get('value')
        id = values.get('id')
        field = values.get('field')
        
        if value is not None and (id is not None or field is not None):
            raise ValueError("Cannot specify both 'value' and ('id', 'field')")
            
        if value is None and (id is None or field is None):
            raise ValueError("Must specify either 'value' or both 'id' and 'field'")
            
        return values
    

if __name__ == "__main__":
    ref = Reference.model_validate(
        {
            "value": "1"
        }
    )
    
    print(ref)