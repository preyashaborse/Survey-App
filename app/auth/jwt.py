from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from core.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    Adds an expiration time to the data ("exp" claim) and signs it with JWT_SECRET_KEY.
    Used when a user logs in.
    
    Args:
        data: Dictionary containing the data to encode (e.g., {"sub": "username"})
        expires_delta: Optional custom expiration time. If None, uses JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    
    Returns:
        The encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not set in environment variables")
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token.
    Verifies the token signature and returns decoded data.
    Returns None if invalid or expired.
    Used when accessing protected routes.
    
    Args:
        token: The JWT token string to decode
    
    Returns:
        The decoded token payload (dict) if valid, None if invalid or expired
    """
    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not set in environment variables")
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None

