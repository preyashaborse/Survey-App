from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.auth.schemas import Token
from app.auth.deps import fake_users_db, get_user
from app.auth.security import verify_password
from app.auth.jwt import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint that authenticates users and returns a JWT token.
    
    Uses OAuth2PasswordRequestForm to automatically accept username and password form fields.
    """
    # Get user from fake database
    user = get_user(fake_users_db, form_data.username)
    
    # Check if user exists
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password using bcrypt
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token with username in the payload
    access_token = create_access_token(data={"sub": user.username})
    
    # Return token response
    return Token(access_token=access_token, token_type="bearer")

