class Node:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
            

# Using your inputs dictionary
inputs = {
    "name": 1,
    "age": 2
}

node = Node(**inputs)

print(node.name)
print(node.age)