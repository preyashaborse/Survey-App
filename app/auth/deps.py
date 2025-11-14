from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.auth.schemas import User, UserInDB
from app.auth.jwt import decode_token

fake_users_db = {
    "preyasha": {
        "username": "preyasha",
        "full_name": "Preyasha Borse",
        "hashed_password": "$2b$12$SPPWqLbqsHGfzW6KuOcb9eHuThd0Ow0B8c1rjJlsZ8M81kFR5sYpK",
        "disabled": False,
    }
}

# OAuth2PasswordBearer automatically reads JWT from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def get_user(db, username: str) -> Optional[UserInDB]:
    user_data = db.get(username)
    if user_data:
        return UserInDB(**user_data)
    return None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    JWT dependency that verifies the token and returns the current user.
    
    - Verifies that a JWT token sent in the request header is valid
    - Decodes it and extracts the username
    - Loads the user from fake DB
    - Automatically passes that user object into any protected route
    
    Returns:
        User object if valid
        
    Raises:
        HTTPException 401 if token is invalid or user not found
    """
    # Decode and verify the token
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract username from token payload (stored in "sub" claim)
    username: Optional[str] = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Look up user in fake database
    user = get_user(fake_users_db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Return User object (without password)
    return User(username=user.username, full_name=user.full_name, disabled=user.disabled)
