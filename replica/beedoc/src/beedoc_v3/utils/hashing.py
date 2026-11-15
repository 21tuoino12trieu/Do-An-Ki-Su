import hashlib

def calculate_file_hash(file_path: str, algorithm: str = "md5") -> str:
    """Calculate the hash of a file to check for duplicates."""
    hash_func = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()
