# The function code stored as a string
code_str = """
from typing import Dict, Any

def calculate_metrics(inputs: Dict[str, Any]) -> Dict[str, Any]:
    products = inputs.get('products', [])
    total_price = sum(product.get('price', 0) for product in products)
    avg_price = total_price / len(products) if products else 0
    
    return {
        'total_price': total_price,
        'avg_price': avg_price,
        'product_count': len(products)
    }
"""

# Create a namespace for the function
namespace = {}

# Execute the code string in the namespace
exec(code_str, namespace)

# Get the function from the namespace
calculate_metrics_callable = namespace['calculate_metrics']

# Now you can use it as a callable function
sample_input = {
    'products': [
        {'name': 'Product 1', 'price': 10.99},
        {'name': 'Product 2', 'price': 24.99},
        {'name': 'Product 3', 'price': 5.49}
    ]
}

# Call the function
result = calculate_metrics_callable(sample_input)
print(result)