import time
import functools

def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        # Return both the original result and the execution time
        return {
            'result': result,
            'execution_time': execution_time
        }
    return wrapper

# Example usage
@timer
def complex_calculation(n):
    """A function that performs some calculation and returns a result."""
    time.sleep(n)  # Simulate work
    return n * n

# Now when you call the function, you get both the result and timing
result = complex_calculation(2)
print(f"Result: {result}")