import hashlib
import secrets
from .config import settings
def generate_api_key() -> str:
    return secrets.token_hex(32)
def hash_api_key(api_key: str) -> str:
    salted = f"{api_key}{settings.api_key_salt}"
    return hashlib.sha256(salted.encode()).hexdigest()
def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    return hash_api_key(plain_key) == hashed_key
