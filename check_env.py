from dotenv import load_dotenv
import os

# Load .env from project root
# override=True ensures .env file values take precedence over system environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

print("API KEY:", os.getenv("OPENAI_API_KEY"))
print("PROJECT ID:", os.getenv("OPENAI_PROJECT_ID"))
