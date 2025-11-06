import os
from dotenv import load_dotenv

# Load environment variables from project root .env file
# override=True ensures .env file values take precedence over system environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)

# JWT Authentication Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")  # Default to HS256 if not specified
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))  # Default to 30 minutes
JWT_REFRESH_TOKEN_EXPIRE_MINUTES = os.getenv("JWT_REFRESH_TOKEN_EXPIRE_MINUTES")  # Optional
SECRET_KEY = os.getenv("SECRET_KEY")  # Alternative naming convention
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")  # Alternative naming convention

