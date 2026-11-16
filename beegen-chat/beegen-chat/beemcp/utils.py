from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import base64


def encrypt(plaintext: str, key: bytes) -> str:
    """
    Encrypt a plaintext string using AES-256 in CBC mode.

    Args:
        plaintext (str): The string to encrypt.
        key (bytes): The 32-byte AES key.

    Returns:
        str: The base64-encoded ciphertext (IV + encrypted data).
    """
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_text = pad(plaintext.encode(), 16)
    ciphertext = cipher.encrypt(padded_text)
    return base64.b64encode(iv + ciphertext).decode()


def decrypt(ciphertext_b64: str, key: bytes) -> str:
    """
    Decrypt a base64-encoded ciphertext string using AES-256 in CBC mode.

    Args:
        ciphertext_b64 (str): The base64-encoded ciphertext (IV + encrypted data).
        key (bytes): The 32-byte AES key.

    Returns:
        str: The decrypted plaintext string.
    """
    raw = base64.b64decode(ciphertext_b64)
    iv = raw[:16]
    ciphertext = raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_plaintext = cipher.decrypt(ciphertext)
    return unpad(padded_plaintext, 16).decode()


if __name__ == "__main__":
    # Example usage of AES-256 encryption and decryption utilities.
    KEY = get_random_bytes(32)  # AES-256 needs a 32-byte key
    original_text = "Hello, AES-256 encryption!"
    ciphertext = encrypt(original_text, KEY)
    decrypted_text = decrypt(ciphertext, KEY)

    print("Original:", original_text)
    print("Encrypted:", ciphertext)
    print("Decrypted:", decrypted_text)
