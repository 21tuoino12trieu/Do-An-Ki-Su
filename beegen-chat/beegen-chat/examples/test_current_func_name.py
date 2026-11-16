import inspect

class MyClass:
    def my_method(self):
        current_method_name = inspect.currentframe().f_code.co_name
        print(f"Current method name: {current_method_name}")
        
obj = MyClass()
obj.my_method()  # Output: Current method name: my_method