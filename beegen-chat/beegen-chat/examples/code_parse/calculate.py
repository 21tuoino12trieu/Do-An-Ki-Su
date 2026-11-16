from typing import Dict, Any

def helper(x) -> float:
    return x * 2

def calculate(data) -> Dict[str, Any]:        
    result = sum(data)
    doubled = helper(result)
    return {'sum': result, 'doubled': doubled}